import tempfile
import unittest
from pathlib import Path

import yaml

from bpo_runtime.configuration import (
    ConfigError,
    go2rtc_config,
    load_config,
    onvif_config,
    overlay_config,
    stream_name,
)


def valid_config() -> dict:
    return {
        "site_label": "LAB",
        "network": {"parent_interface": "br0"},
        "video": {"framerate": 15, "bitrate_kbps": 3072},
        "printers": [{
            "name": "Printer One",
            "host": "192.168.1.50",
            "access_code": "a:b@c",
            "serial": "SERIAL-ONE",
            "onvif": {
                "ip": "192.168.1.211/24",
                "mac": "02:00:00:00:00:01",
                "uuid": "2e534a2f-f35d-48f9-a916-a2d16cfa0903",
                "ports": {"server": 11000, "rtsp": 11001, "snapshot": 11002},
            },
        }],
    }


class ConfigurationTests(unittest.TestCase):
    def load(self, value: dict) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(yaml.safe_dump(value), encoding="utf-8")
            return load_config(path)

    def test_loads_and_normalizes_config(self):
        config = self.load(valid_config())
        printer = config["printers"][0]

        self.assertEqual(printer["stream_name"], "printer_one")
        self.assertEqual(printer["user"], "bblp")
        self.assertEqual(printer["onvif"]["mac"], "02:00:00:00:00:01")
        self.assertEqual(config["video"]["framerate"], 15)
        self.assertEqual(config["video"]["height"], 1080)

    def test_generates_all_runtime_configs(self):
        config = self.load(valid_config())
        go2rtc = go2rtc_config(config)
        onvif = onvif_config(config)
        overlay = overlay_config(config)

        source = go2rtc["streams"]["printer_one_src"]
        self.assertIn("a%3Ab%40c@192.168.1.50", source)
        self.assertEqual(go2rtc["streams"]["printer_one"], "ffmpeg:printer_one_src#video=drawtext=printer_one")
        self.assertIn("/data/overlay/printer_one_4.txt", go2rtc["ffmpeg"]["drawtext=printer_one"])
        self.assertEqual(onvif["onvif"][0]["target"]["hostname"], "127.0.0.1")
        self.assertEqual(onvif["onvif"][0]["highQuality"]["rtsp"], "/printer_one")
        self.assertEqual(overlay["printers"][0]["stream_name"], "printer_one")

    def test_rejects_duplicate_listener_port(self):
        value = valid_config()
        second = yaml.safe_load(yaml.safe_dump(value["printers"][0]))
        second.update({"name": "Two", "host": "192.168.1.51", "serial": "SERIAL-TWO"})
        second["onvif"].update({
            "ip": "192.168.1.212/24",
            "mac": "02:00:00:00:00:02",
            "uuid": "9ab94892-50e9-42f6-8c86-e0a14a2ac77f",
        })
        value["printers"].append(second)

        with self.assertRaisesRegex(ConfigError, "duplicate or reserved listener port"):
            self.load(value)

    def test_rejects_non_local_mac(self):
        value = valid_config()
        value["printers"][0]["onvif"]["mac"] = "00:00:00:00:00:01"
        with self.assertRaisesRegex(ConfigError, "locally administered"):
            self.load(value)

    def test_rejects_network_address(self):
        value = valid_config()
        value["printers"][0]["onvif"]["ip"] = "192.168.1.0/24"
        with self.assertRaisesRegex(ConfigError, "network or broadcast"):
            self.load(value)

    def test_stream_name_requires_alphanumeric_content(self):
        self.assertEqual(stream_name("A1 Mini"), "a1_mini")
        with self.assertRaises(ConfigError):
            stream_name("---")

    def test_rejects_fractional_and_boolean_integers(self):
        for value in (15.5, True):
            config = valid_config()
            config["video"]["framerate"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ConfigError, "must be an integer"):
                self.load(config)


if __name__ == "__main__":
    unittest.main()
