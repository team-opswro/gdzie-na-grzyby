"""Healthcheck kontenera forecast: pogoda.json młodszy niż 36 h."""
import sys
import time
from pathlib import Path

MAX_AGE_H = 36


def is_fresh(path: Path, max_age_h: float = MAX_AGE_H, now: float | None = None) -> bool:
    try:
        mtime = Path(path).stat().st_mtime
    except OSError:
        return False
    now = time.time() if now is None else now
    return (now - mtime) <= max_age_h * 3600


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "/out/pogoda.json")
    sys.exit(0 if is_fresh(target) else 1)
