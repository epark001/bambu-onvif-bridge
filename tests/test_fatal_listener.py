import io
import unittest
from unittest.mock import patch

from bpo_runtime.fatal_listener import main


class FatalListenerTests(unittest.TestCase):
    @patch("bpo_runtime.fatal_listener.os.kill")
    @patch("bpo_runtime.fatal_listener.os.getppid", return_value=42)
    def test_stops_supervisor_on_fatal_process(self, _getppid, kill):
        payload = "processname:network groupname:network"
        header = f"eventname:PROCESS_STATE_FATAL len:{len(payload)}\n"
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch("sys.stdin", io.StringIO(header + payload)),
            patch("sys.stdout", stdout),
            patch("sys.stderr", stderr),
        ):
            main()

        self.assertEqual(stdout.getvalue(), "READY\nRESULT 2\nOK")
        self.assertIn("network", stderr.getvalue())
        kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()
