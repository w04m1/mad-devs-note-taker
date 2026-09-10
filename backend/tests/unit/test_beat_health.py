from pathlib import Path

from app.jobs.beat import record_successful_publication


def test_beat_publication_signal_is_atomically_replaced(tmp_path: Path) -> None:
    signal = tmp_path / "beat-published"
    record_successful_publication(signal)
    first = signal.stat().st_mtime_ns
    record_successful_publication(signal)
    assert signal.read_text(encoding="ascii") == "published\n"
    assert signal.stat().st_mtime_ns >= first
    assert list(tmp_path.iterdir()) == [signal]
