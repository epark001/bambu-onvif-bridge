import socket
import subprocess
import sys
import time
from pathlib import Path

from .configuration import OVERLAY_DIR, RUNTIME_DIR, ConfigError, load_config


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def listener_open(port: int) -> bool:
    encoded_port = f"{port:04X}"
    for proc_path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = Path(proc_path).read_text(encoding="ascii").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            columns = line.split()
            if columns[1].rsplit(":", 1)[-1] == encoded_port and columns[3] == "0A":
                return True
    return False


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1

    status = subprocess.run(
        ["supervisorctl", "-c", "/etc/supervisord.conf", "status"],
        check=False,
        text=True,
        capture_output=True,
    )
    if status.returncode != 0 or any(
        state in status.stdout for state in ("BACKOFF", "EXITED", "FATAL", "STOPPED")
    ):
        print(status.stdout or status.stderr, file=sys.stderr)
        return 1

    if not (RUNTIME_DIR / "network-ready").exists() or not port_open(1984) or not port_open(8554):
        print("runtime dependencies are not ready", file=sys.stderr)
        return 1

    now = time.time()
    for index, printer in enumerate(config["printers"]):
        interface = Path(f"/sys/class/net/bpo-onvif{index}")
        if not interface.exists():
            print(f"missing virtual interface: {interface.name}", file=sys.stderr)
            return 1
        for port in printer["onvif"]["ports"].values():
            if not listener_open(port):
                print(f"ONVIF listener {port} is unavailable for {printer['name']}", file=sys.stderr)
                return 1
        overlay = OVERLAY_DIR / f"{printer['stream_name']}_1.txt"
        if not overlay.exists() or now - overlay.stat().st_mtime > 10:
            print(f"overlay output is stale for {printer['name']}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
