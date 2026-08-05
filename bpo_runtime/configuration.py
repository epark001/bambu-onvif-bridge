from __future__ import annotations

import ipaddress
import os
import re
import uuid
from pathlib import Path
from urllib.parse import quote

import yaml

CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", "/config/config.yaml"))
RUNTIME_DIR = Path(os.environ.get("RUNTIME_DIR", "/run/bambu-protect-overlay"))
OVERLAY_DIR = Path(os.environ.get("OUTPUT_DIR", "/data/overlay"))

DEFAULT_VIDEO = {
    "width": 1680,
    "height": 1080,
    "framerate": 30,
    "bitrate_kbps": 4096,
    "maxrate_kbps": 5120,
    "buffer_kbps": 10240,
    "preset": "veryfast",
    "font_size": 26,
    "bar_height": 180,
}

MAC_RE = re.compile(r"^(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")
SAFE_NAME_RE = re.compile(r"[^a-z0-9]+")
INTERFACE_RE = re.compile(r"^[a-zA-Z0-9_.:-]+$")


class ConfigError(ValueError):
    pass


def stream_name(name: str) -> str:
    value = SAFE_NAME_RE.sub("_", name.strip().lower()).strip("_")
    if not value:
        raise ConfigError(f"printer name {name!r} does not produce a valid stream name")
    return value


def _integer(value, path: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or isinstance(value, float) and not value.is_integer():
        raise ConfigError(f"{path} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{path} must be an integer") from exc
    if not minimum <= result <= maximum:
        raise ConfigError(f"{path} must be between {minimum} and {maximum}")
    return result


def _required(mapping: dict, key: str, path: str):
    value = mapping.get(key)
    if value is None or value == "":
        raise ConfigError(f"{path}.{key} is required")
    return value


def _validate_mac(value: str, path: str) -> str:
    if not MAC_RE.fullmatch(value):
        raise ConfigError(f"{path} must be a colon-delimited MAC address")
    normalized = value.lower()
    first = int(normalized[:2], 16)
    if first & 1:
        raise ConfigError(f"{path} must be a unicast MAC address")
    if not first & 2:
        raise ConfigError(f"{path} must be locally administered")
    return normalized


def load_config(path: Path = CONFIG_PATH) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("configuration must be a YAML mapping")

    network = raw.get("network")
    if not isinstance(network, dict):
        raise ConfigError("network must be a mapping")
    parent = _required(network, "parent_interface", "network")
    if not isinstance(parent, str) or len(parent) > 15 or not INTERFACE_RE.fullmatch(parent):
        raise ConfigError("network.parent_interface must be a Linux interface name")

    video_raw = raw.get("video", {})
    if not isinstance(video_raw, dict):
        raise ConfigError("video must be a mapping")
    video = DEFAULT_VIDEO | video_raw
    for key in ("width", "height"):
        video[key] = _integer(video[key], f"video.{key}", 1, 8192)
    video["framerate"] = _integer(video["framerate"], "video.framerate", 1, 120)
    for key in ("bitrate_kbps", "maxrate_kbps", "buffer_kbps"):
        video[key] = _integer(video[key], f"video.{key}", 1, 100000)
    video["font_size"] = _integer(video["font_size"], "video.font_size", 8, 200)
    video["bar_height"] = _integer(video["bar_height"], "video.bar_height", 1, video["height"])
    if not isinstance(video["preset"], str) or video["preset"] not in {
        "ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"
    }:
        raise ConfigError("video.preset is not a supported libx264 preset")

    printers_raw = raw.get("printers")
    if not isinstance(printers_raw, list) or not printers_raw:
        raise ConfigError("printers must be a non-empty list")

    printers = []
    names: set[str] = set()
    hosts: set[str] = set()
    macs: set[str] = set()
    ips: set[ipaddress.IPv4Address] = set()
    uuids: set[str] = set()
    ports: set[int] = {1984, 8554}

    for index, item in enumerate(printers_raw):
        path_prefix = f"printers[{index}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{path_prefix} must be a mapping")

        name = str(_required(item, "name", path_prefix)).strip()
        slug = stream_name(name)
        if slug in names:
            raise ConfigError(f"duplicate printer stream name: {slug}")
        names.add(slug)

        host = str(_required(item, "host", path_prefix)).strip()
        try:
            printer_ip = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ConfigError(f"{path_prefix}.host must be a valid IPv4 address") from exc
        if not isinstance(printer_ip, ipaddress.IPv4Address):
            raise ConfigError(f"{path_prefix}.host must be IPv4")
        if host in hosts:
            raise ConfigError(f"duplicate printer host: {host}")
        hosts.add(host)

        access_code = item.get("access_code", item.get("pass"))
        if not access_code:
            raise ConfigError(f"{path_prefix}.access_code is required")

        onvif = item.get("onvif")
        if not isinstance(onvif, dict):
            raise ConfigError(f"{path_prefix}.onvif must be a mapping")

        try:
            virtual_ip = ipaddress.ip_interface(_required(onvif, "ip", f"{path_prefix}.onvif"))
        except ValueError as exc:
            raise ConfigError(f"{path_prefix}.onvif.ip must be a valid IPv4 CIDR address") from exc
        if not isinstance(virtual_ip, ipaddress.IPv4Interface):
            raise ConfigError(f"{path_prefix}.onvif.ip must be IPv4")
        if virtual_ip.ip.is_loopback or virtual_ip.ip.is_multicast or virtual_ip.ip.is_unspecified:
            raise ConfigError(f"{path_prefix}.onvif.ip is not a usable LAN address")
        if virtual_ip.ip in (virtual_ip.network.network_address, virtual_ip.network.broadcast_address):
            raise ConfigError(f"{path_prefix}.onvif.ip cannot be the network or broadcast address")
        if virtual_ip.ip == printer_ip:
            raise ConfigError(f"{path_prefix}.onvif.ip cannot match the printer host")
        if virtual_ip.ip in ips:
            raise ConfigError(f"duplicate ONVIF IP: {virtual_ip.ip}")
        ips.add(virtual_ip.ip)

        mac = _validate_mac(str(_required(onvif, "mac", f"{path_prefix}.onvif")), f"{path_prefix}.onvif.mac")
        if mac in macs:
            raise ConfigError(f"duplicate ONVIF MAC: {mac}")
        macs.add(mac)

        uuid_value = str(_required(onvif, "uuid", f"{path_prefix}.onvif"))
        try:
            uuid_value = str(uuid.UUID(uuid_value))
        except ValueError as exc:
            raise ConfigError(f"{path_prefix}.onvif.uuid must be a valid UUID") from exc
        if uuid_value in uuids:
            raise ConfigError(f"duplicate ONVIF UUID: {uuid_value}")
        uuids.add(uuid_value)

        port_values = onvif.get("ports")
        if not isinstance(port_values, dict):
            raise ConfigError(f"{path_prefix}.onvif.ports must be a mapping")
        normalized_ports = {}
        for key in ("server", "rtsp", "snapshot"):
            port = _integer(port_values.get(key), f"{path_prefix}.onvif.ports.{key}", 1, 65535)
            if port in ports:
                raise ConfigError(f"duplicate or reserved listener port: {port}")
            ports.add(port)
            normalized_ports[key] = port

        printers.append({
            "name": name,
            "stream_name": slug,
            "host": host,
            "user": str(item.get("user", "bblp")),
            "pass": str(access_code),
            "serial": str(_required(item, "serial", path_prefix)),
            "onvif": {
                "ip": str(virtual_ip),
                "mac": mac,
                "uuid": uuid_value,
                "ports": normalized_ports,
            },
        })

    return {
        "site_label": str(raw.get("site_label", "BAMBU")),
        "line_width": _integer(raw.get("line_width", 80), "line_width", 20, 200),
        "network": {"parent_interface": parent},
        "video": video,
        "printers": printers,
    }


def overlay_config(config: dict) -> dict:
    return {
        "site_label": config["site_label"],
        "line_width": config["line_width"],
        "printers": [
            {key: printer[key] for key in ("name", "stream_name", "host", "user", "pass", "serial")}
            for printer in config["printers"]
        ],
    }


def _ffmpeg_template(slug: str, video: dict) -> str:
    bar = video["bar_height"]
    font = video["font_size"]
    padding = max(10, font // 2)
    spacing = max(font + 8, (bar - padding * 2) // 4)
    first_y = bar - padding
    filters = [f"drawbox=x=0:y=ih-{bar}:w=iw:h={bar}:color=black@0.55:t=fill"]
    for index in range(4):
        y_offset = first_y - spacing * index
        filters.append(
            "drawtext="
            f"textfile={OVERLAY_DIR}/{slug}_{index + 1}.txt:reload=1:expansion=none:"
            f"fontfile=/usr/share/fonts/droid/DroidSansMono.ttf:fontsize={font}:"
            f"fontcolor=white:x=20:y=h-{y_offset}"
        )
    filter_value = ",".join(filters)
    fps = video["framerate"]
    return (
        f"-c:v libx264 -profile:v baseline -level:v 4.0 -preset:v {video['preset']} "
        f"-pix_fmt:v yuv420p -r {fps} -g:v {fps} -keyint_min:v {fps} "
        f"-sc_threshold:v 0 -b:v {video['bitrate_kbps']}k "
        f"-maxrate:v {video['maxrate_kbps']}k -bufsize:v {video['buffer_kbps']}k "
        f'-vf "{filter_value}"'
    )


def go2rtc_config(config: dict) -> dict:
    streams = {}
    ffmpeg = {}
    for printer in config["printers"]:
        slug = printer["stream_name"]
        user = quote(printer["user"], safe="")
        password = quote(printer["pass"], safe="")
        streams[f"{slug}_src"] = (
            f"rtspx://{user}:{password}@{printer['host']}:322/streaming/live/1"
        )
        streams[slug] = f"ffmpeg:{slug}_src#video=drawtext={slug}"
        ffmpeg[f"drawtext={slug}"] = _ffmpeg_template(slug, config["video"])
    return {"streams": streams, "ffmpeg": ffmpeg}


def onvif_config(config: dict) -> dict:
    video = config["video"]
    entries = []
    for printer in config["printers"]:
        slug = printer["stream_name"]
        entries.append({
            "mac": printer["onvif"]["mac"],
            "ports": printer["onvif"]["ports"],
            "name": printer["name"],
            "uuid": printer["onvif"]["uuid"],
            "highQuality": {
                "rtsp": f"/{slug}",
                "snapshot": f"/api/frame.jpeg?src={slug}",
                "width": video["width"],
                "height": video["height"],
                "framerate": video["framerate"],
                "bitrate": video["bitrate_kbps"],
                "quality": 4,
            },
            "target": {
                "hostname": "127.0.0.1",
                "ports": {"rtsp": 8554, "snapshot": 1984},
            },
        })
    return {"onvif": entries}


def write_yaml(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(value, handle, sort_keys=False, default_flow_style=False)
    temporary.chmod(0o600)
    temporary.replace(path)
