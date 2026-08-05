from __future__ import annotations

import json
import logging
import signal
import subprocess
import sys
import threading

from .configuration import RUNTIME_DIR, ConfigError, load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] network: %(message)s")
log = logging.getLogger("network")
STOP = threading.Event()


class NetworkError(RuntimeError):
    pass


def run_ip(*arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ip", *arguments], check=check, text=True, capture_output=True
    )


def interface_state(name: str) -> dict | None:
    result = run_ip("-j", "-d", "address", "show", "dev", name, check=False)
    if result.returncode != 0:
        return None
    entries = json.loads(result.stdout)
    return entries[0] if entries else None


def all_interface_states() -> list[dict]:
    result = run_ip("-j", "-d", "address", "show")
    return json.loads(result.stdout)


def address_owners(address: str, states: list[dict]) -> set[str]:
    expected_ip = address.split("/", 1)[0]
    return {
        state["ifname"]
        for state in states
        for item in state.get("addr_info", [])
        if item.get("family") == "inet" and item.get("local") == expected_ip
    }


def ensure_interface(name: str, parent: str, mac: str, address: str) -> None:
    current = interface_state(name)
    expected_ip, expected_prefix = address.split("/", 1)
    if current:
        parent_state = interface_state(parent)
        current_ips = {
            (item["local"], str(item["prefixlen"]))
            for item in current.get("addr_info", [])
            if item.get("family") == "inet"
        }
        link_info = current.get("linkinfo", {})
        info_data = link_info.get("info_data", {})
        if (
            current.get("address", "").lower() != mac
            or (expected_ip, expected_prefix) not in current_ips
            or link_info.get("info_kind") != "macvlan"
            or info_data.get("mode") != "bridge"
            or not parent_state
            or (
                current.get("link") != parent
                and current.get("link_index") != parent_state.get("ifindex")
            )
        ):
            raise NetworkError(
                f"existing interface {name} does not match the configured macvlan; refusing to alter it"
            )
        run_ip("link", "set", name, "up")
        log.info("reusing interface %s (%s, %s)", name, mac, address)
        return

    run_ip(
        "link", "add", name, "link", parent, "address", mac,
        "type", "macvlan", "mode", "bridge",
    )
    try:
        run_ip("address", "add", address, "dev", name)
        run_ip("link", "set", name, "up")
    except Exception:
        run_ip("link", "delete", name, check=False)
        raise
    log.info("created interface %s on %s (%s, %s)", name, parent, mac, address)


def remove_interface(name: str) -> None:
    if interface_state(name):
        result = run_ip("link", "delete", name, check=False)
        if result.returncode == 0:
            log.info("removed interface %s", name)
        else:
            log.warning("could not remove interface %s: %s", name, result.stderr.strip())


def main() -> int:
    try:
        config = load_config()
        parent = config["network"]["parent_interface"]
        if interface_state(parent) is None:
            raise NetworkError(f"parent interface does not exist: {parent}")

        managed = []
        for index, printer in enumerate(config["printers"]):
            name = f"bpo-onvif{index}"
            owners = address_owners(printer["onvif"]["ip"], all_interface_states()) - {name}
            if owners:
                raise NetworkError(
                    f"ONVIF IP {printer['onvif']['ip']} is already assigned to: {', '.join(sorted(owners))}"
                )
            ensure_interface(name, parent, printer["onvif"]["mac"], printer["onvif"]["ip"])
            managed.append(name)

        ready_path = RUNTIME_DIR / "network-ready"
        ready_path.touch()
        log.info("all virtual camera interfaces are ready")
        STOP.wait()
    except (ConfigError, NetworkError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        log.error("network setup failed: %s", exc)
        return 1
    finally:
        try:
            (RUNTIME_DIR / "network-ready").unlink(missing_ok=True)
        except OSError:
            pass
        for name in reversed(locals().get("managed", [])):
            remove_interface(name)
    return 0


def stop(_signum, _frame) -> None:
    STOP.set()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    sys.exit(main())
