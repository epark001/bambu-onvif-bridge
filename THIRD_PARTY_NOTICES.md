# Third-Party Notices

## Original project

Bambu ONVIF Bridge is derived from
[bambu-protect-overlay](https://github.com/mtnears/bambu-protect-overlay).

- Copyright: 2026 Ken Pauley
- License: MIT

The combined container includes the following projects:

## go2rtc

- Project: <https://github.com/AlexxIT/go2rtc>
- Bundled version: 1.9.14
- Copyright: 2022 Alexey Khit
- License: MIT

## Virtual ONVIF Server

- Project: <https://github.com/daniela-hase/onvif-server>
- Bundled commit: `7aa2c541b67b1a2760887a1706d7a5e45e5ae1a4`
- Copyright: 2024 Daniela Hasenbring
- License: MIT

The container updates the upstream `xml2js` and `yaml` dependency pins to
compatible patched releases because the original versions have published
moderate-severity security advisories.

The full license text for this project and both bundled projects is the MIT
License reproduced in `LICENSE`. Node.js and Python dependencies retain their
own license metadata inside the container image.
