"""Exit successfully only while Celery Beat has recently published to its broker."""

from __future__ import annotations

import os
import time
from pathlib import Path

path = Path(os.environ.get("BEAT_FRESHNESS_PATH", "/tmp/beat-published"))
maximum_age = float(os.environ.get("BEAT_HEALTH_MAX_AGE_SECONDS", "15"))
try:
    age = time.time() - path.stat().st_mtime
except OSError:
    raise SystemExit(1) from None
raise SystemExit(0 if 0 <= age <= maximum_age else 1)
