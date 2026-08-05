import unittest
from unittest.mock import call, patch

from bpo_runtime.network_manager import NetworkError, ensure_interface


class NetworkManagerTests(unittest.TestCase):
    @patch("bpo_runtime.network_manager.run_ip")
    @patch("bpo_runtime.network_manager.interface_state", return_value=None)
    def test_creates_macvlan(self, _state, run_ip):
        ensure_interface("bpo-onvif0", "br0", "02:00:00:00:00:01", "192.168.1.211/24")
        self.assertEqual(run_ip.call_args_list, [
            call(
                "link", "add", "bpo-onvif0", "link", "br0", "address",
                "02:00:00:00:00:01", "type", "macvlan", "mode", "bridge",
            ),
            call("address", "add", "192.168.1.211/24", "dev", "bpo-onvif0"),
            call("link", "set", "bpo-onvif0", "up"),
        ])

    @patch("bpo_runtime.network_manager.run_ip")
    @patch("bpo_runtime.network_manager.interface_state")
    def test_reuses_exact_interface(self, state, run_ip):
        current = {
            "address": "02:00:00:00:00:01",
            "link": "br0",
            "linkinfo": {"info_kind": "macvlan", "info_data": {"mode": "bridge"}},
            "addr_info": [{"family": "inet", "local": "192.168.1.211", "prefixlen": 24}],
        }
        parent = {"ifindex": 4}
        state.side_effect = [current, parent]
        ensure_interface("bpo-onvif0", "br0", "02:00:00:00:00:01", "192.168.1.211/24")
        run_ip.assert_called_once_with("link", "set", "bpo-onvif0", "up")

    @patch("bpo_runtime.network_manager.run_ip")
    @patch("bpo_runtime.network_manager.interface_state")
    def test_refuses_mismatched_interface(self, state, run_ip):
        state.return_value = {
            "address": "02:00:00:00:00:99",
            "addr_info": [{"family": "inet", "local": "192.168.1.211", "prefixlen": 24}],
        }
        with self.assertRaises(NetworkError):
            ensure_interface("bpo-onvif0", "br0", "02:00:00:00:00:01", "192.168.1.211/24")
        run_ip.assert_not_called()

    @patch("bpo_runtime.network_manager.run_ip")
    @patch("bpo_runtime.network_manager.interface_state")
    def test_refuses_wrong_interface_type(self, state, run_ip):
        state.side_effect = [{
            "address": "02:00:00:00:00:01",
            "link": "br0",
            "linkinfo": {"info_kind": "vlan", "info_data": {}},
            "addr_info": [{"family": "inet", "local": "192.168.1.211", "prefixlen": 24}],
        }, {"ifindex": 4}]
        with self.assertRaises(NetworkError):
            ensure_interface("bpo-onvif0", "br0", "02:00:00:00:00:01", "192.168.1.211/24")
        run_ip.assert_not_called()


if __name__ == "__main__":
    unittest.main()
