import os
import socket
import sys
import time

from .configuration import RUNTIME_DIR


def main() -> int:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        network_ready = (RUNTIME_DIR / "network-ready").exists()
        try:
            with socket.create_connection(("127.0.0.1", 1984), timeout=1):
                go2rtc_ready = True
        except OSError:
            go2rtc_ready = False
        if network_ready and go2rtc_ready:
            os.chdir("/opt/onvif-server")
            os.execvp("node", ["node", "/opt/onvif-server/main.js", str(RUNTIME_DIR / "onvif.yaml")])
        time.sleep(1)
    print("onvif: dependencies did not become ready within 60 seconds", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
