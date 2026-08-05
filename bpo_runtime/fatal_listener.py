import os
import signal
import sys


def main() -> None:
    while True:
        sys.stdout.write("READY\n")
        sys.stdout.flush()
        header = sys.stdin.readline()
        if not header:
            return
        fields = dict(item.split(":", 1) for item in header.split() if ":" in item)
        payload = sys.stdin.read(int(fields.get("len", "0")))
        process = next(
            (item.split(":", 1)[1] for item in payload.split() if item.startswith("processname:")),
            "unknown",
        )
        print(f"required process entered FATAL state: {process}", file=sys.stderr, flush=True)
        sys.stdout.write("RESULT 2\nOK")
        sys.stdout.flush()
        os.kill(os.getppid(), signal.SIGTERM)
        return


if __name__ == "__main__":
    main()
