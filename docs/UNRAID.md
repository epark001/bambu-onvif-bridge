# Unraid Single-Container Installation

The single-container image runs the MQTT overlay writer, go2rtc/FFmpeg, and
the ONVIF wrapper together. It also creates the virtual macvlan interfaces
that UniFi Protect needs, so no Unraid boot script is required.

## Requirements

- Unraid connected to the same wired LAN as the printers and UniFi Protect
- One unused static LAN address per printer, outside the DHCP allocation pool
- One unique locally administered MAC and UUID per printer
- Free host ports `1984`, `8554`, and three `11000`-range ports per printer
- A switch port that permits multiple source MAC addresses

The container uses host networking and the `NET_ADMIN` capability. This lets
its network manager add and remove interfaces in the host network namespace.
Only run images you trust with this capability.

## Prepare Appdata

Create the appdata directory and copy the example configuration into it:

```bash
mkdir -p /mnt/user/appdata/bambu-protect-overlay
curl -fsSL \
  https://raw.githubusercontent.com/epark001/bambu-protect-overlay/main/config.unraid.example.yaml \
  -o /mnt/user/appdata/bambu-protect-overlay/config.yaml
```

Edit `config.yaml` and replace every example address, credential, serial,
MAC, and UUID.

## Find the Parent Interface

Open an Unraid terminal and run:

```bash
ip -br address
```

The parent is normally `br0`. VLAN installations may use an interface such
as `br0.20`. Set the exact name under `network.parent_interface`.

## Configure Virtual Cameras

Each printer entry requires:

| Setting | Purpose |
|---|---|
| `host` | Printer's LAN IPv4 address |
| `access_code` | Bambu LAN access code |
| `serial` | Printer certificate serial/CN |
| `onvif.ip` | Unused static IPv4 address with prefix, such as `/24` |
| `onvif.mac` | Unique locally administered unicast MAC |
| `onvif.uuid` | Unique UUID |
| `onvif.ports` | Three unique, unused host ports |

The configuration validator rejects duplicate names, printer addresses,
virtual addresses, MACs, UUIDs, and listener ports before starting services.
It also rejects the host's go2rtc ports (`1984` and `8554`) as ONVIF ports.

For a second printer, duplicate the complete printer entry and change all
printer and ONVIF values. Keep the entries in a stable order because the
managed interface names (`bpo-onvif0`, `bpo-onvif1`, and so on) follow list
order.

## Install the Container

The included template is `unraid/bambu-protect-overlay.xml`. Its effective
Docker settings are:

| Unraid field | Value |
|---|---|
| Repository | `ghcr.io/epark001/bambu-protect-overlay:latest` |
| Network type | Host |
| Privileged | No |
| Extra parameters | `--cap-add=NET_ADMIN --restart=unless-stopped --log-opt max-size=50m --log-opt max-file=3` |
| Appdata path | `/mnt/user/appdata/bambu-protect-overlay` to `/config` (read-only) |
| Variable | `TZ`, set to your IANA timezone |

Until the template is available through Community Applications, use Unraid's
**Add Container** screen with those values. After starting it, the go2rtc UI
is available at `http://<unraid-ip>:1984/`.

Because host networking ignores Docker port mappings, changing a port in the
Unraid template does not remap it. Resolve host port conflicts in the
application configuration or on the conflicting application.

## Verify Startup

The logs should show this sequence:

1. Configuration validated and three runtime files generated.
2. One `bpo-onvifN` interface created per printer.
3. MQTT overlay, go2rtc, and ONVIF processes enter `RUNNING` state.
4. Each printer reports an MQTT connection when it is online.

Useful checks from an Unraid terminal:

```bash
docker logs bambu-protect-overlay
docker inspect --format '{{.State.Health.Status}}' bambu-protect-overlay
ip -br address show bpo-onvif0
```

Open `rtsp://<unraid-ip>:8554/<normalized-name>` in VLC using RTSP over TCP.
A name such as `A1 Mini` becomes the stream name `a1_mini`.

## Adopt in UniFi Protect

Enable third-party camera discovery under Protect **Settings > System**.
Each configured virtual address should appear as a separate ONVIF camera.
Adopt it with any username and password; the wrapper does not enforce those
credentials.

## Network Lifecycle

On normal shutdown, the container removes only its validated
`bpo-onvifN` interfaces. After an unclean stop, a later start reuses an
interface only when both its MAC and IP/prefix exactly match the config. A
mismatch causes startup to fail without altering the existing interface.

If a stale mismatched interface remains, inspect it before deleting it:

```bash
ip -details address show bpo-onvif0
ip link delete bpo-onvif0
```

## Updates and Backups

All authoritative state is in `/config/config.yaml`. The generated go2rtc and
ONVIF files and overlay text are recreated at startup. Back up the appdata
directory, then use Unraid's normal container update action to pull a newer
image.

Release tags such as `v1.0.0` are immutable deployment choices. `latest`
tracks the current default-branch build.

## Security Notes

The go2rtc API and RTSP stream use host ports `1984` and `8554`. The ONVIF
proxy listeners use their configured ports. These services are intended for
a trusted LAN and are not safe to expose through router port forwarding.
The `config.yaml` appdata mount is read-only inside the container, and the
generated files containing access codes are written with owner-only
permissions under the container's temporary `/run` directory.
