"""Celery Beat scheduler with a container-local successful-publication signal."""

from __future__ import annotations

import os
from pathlib import Path

from celery.beat import PersistentScheduler

FRESHNESS_PATH = Path(os.environ.get("BEAT_FRESHNESS_PATH", "/tmp/beat-published"))


def record_successful_publication(path: Path = FRESHNESS_PATH) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text("published\n", encoding="ascii")
    os.replace(temporary, path)


class FreshnessScheduler(PersistentScheduler):
    """Advance freshness only after Beat itself successfully publishes a task."""

    def apply_async(self, entry, producer=None, advance=True, **kwargs):
        result = super().apply_async(entry, producer=producer, advance=advance, **kwargs)
        record_successful_publication()
        return result
