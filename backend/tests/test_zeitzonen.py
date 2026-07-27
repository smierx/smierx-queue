"""Postgres gibt Naiv-Lokal-Spalten (TimeBlock, TaskPhase) mit Session-TZ-Label
zurück. Die SQLite-Testsuite sieht das nie, darum stellen diese Tests die
aware Werte direkt nach: die API muss das Label abstreifen, sonst macht der
Browser aus 10:00 Wandzeit 12:00 lokale Zeit."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.schemas import PhaseOut, TimeBlockOut

ZEHN_UHR_MIT_LABEL = datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc)


def test_timeblock_out_streift_label_ab():
    block = SimpleNamespace(
        id=1, titel="Daily", typ="meeting",
        start=ZEHN_UHR_MIT_LABEL,
        ende=ZEHN_UHR_MIT_LABEL.replace(hour=11),
    )
    out = TimeBlockOut.model_validate(block)
    assert out.start.tzinfo is None
    assert out.start.hour == 10
    assert "Z" not in out.model_dump_json()


def test_phase_out_streift_label_ab():
    phase = SimpleNamespace(id=1, task_id=2, von=ZEHN_UHR_MIT_LABEL, bis=None)
    out = PhaseOut.model_validate(phase)
    assert out.von.tzinfo is None
    assert out.von.hour == 10


def test_naive_werte_bleiben_unveraendert():
    block = SimpleNamespace(
        id=1, titel="Daily", typ="meeting",
        start=datetime(2026, 7, 27, 10, 0),
        ende=datetime(2026, 7, 27, 11, 0),
    )
    out = TimeBlockOut.model_validate(block)
    assert out.start == datetime(2026, 7, 27, 10, 0)
