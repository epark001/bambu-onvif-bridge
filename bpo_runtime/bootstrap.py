import logging
import sys

from .configuration import (
    CONFIG_PATH,
    OVERLAY_DIR,
    RUNTIME_DIR,
    ConfigError,
    go2rtc_config,
    load_config,
    onvif_config,
    overlay_config,
    write_yaml,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] bootstrap: %(message)s")
log = logging.getLogger("bootstrap")


def main() -> int:
    try:
        config = load_config()
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
        write_yaml(RUNTIME_DIR / "printers.yaml", overlay_config(config))
        write_yaml(RUNTIME_DIR / "go2rtc.yaml", go2rtc_config(config))
        write_yaml(RUNTIME_DIR / "onvif.yaml", onvif_config(config))
    except ConfigError as exc:
        log.error("configuration error: %s", exc)
        return 1
    except OSError as exc:
        log.error("could not prepare runtime configuration: %s", exc)
        return 1

    log.info("validated %s", CONFIG_PATH)
    log.info("prepared runtime configuration for %d printer(s)", len(config["printers"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
