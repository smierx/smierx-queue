from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# JSONB auf Postgres, JSON-Fallback auf z.B. SQLite (Tests).
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")

# Status als Tag-System: fester Katalog, mehrere Tags pro Task erlaubt.
# `aktiv` steuert die Sektion "läuft gerade", `next` markiert den nächsten Griff.
VALID_TAGS = {
    "aktiv",
    "inaktiv",
    "pausiert",
    "holding",
    "next",
    "discussion",
    "critical",
}

# Zustand-Tags schließen sich gegenseitig aus: einen setzen wirft die anderen runter.
# Marker (discussion, critical) sind frei kombinierbar.
ZUSTAND_TAGS = {"aktiv", "next", "pausiert", "holding", "inaktiv"}

# Support ist bewusst ein Blocker-Typ und kein Task-Tag: Support-Zeit blockt den Tag.
TIMEBLOCK_TYPEN = {"meeting", "blocker", "support"}
SCHEDULE_MODI = {"stunden", "feste_zeiten"}


def _lokal(zeitpunkt: datetime) -> datetime:
    """DB-Defaults sind UTC (SQLite naiv, Postgres aware) → lokale, naive Zeit,
    konsistent zu den TimeBlocks."""
    if zeitpunkt.tzinfo is None:
        zeitpunkt = zeitpunkt.replace(tzinfo=timezone.utc)
    return zeitpunkt.astimezone().replace(tzinfo=None)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    titel: Mapped[str] = mapped_column(String(300))
    beschreibung: Mapped[str] = mapped_column(Text, default="")
    # Queue-Reihenfolge, klein = weiter oben. Reorder schreibt die Positionen neu.
    position: Mapped[int] = mapped_column(Integer, index=True)
    # Geplante Dauer in Minuten, Default eine Stunde. Bestimmt die Balkenbreite im Zeitstrahl.
    dauer_minuten: Mapped[int] = mapped_column(Integer, default=60, server_default="60")
    # Gesetzt = Task ist erledigt und raus aus der Queue, bleibt aber als Archiv erhalten.
    erledigt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    geaendert_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tag_zeilen: Mapped[list["TaskTag"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    historie: Mapped[list["TagEvent"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="TagEvent.id"
    )

    @property
    def tags(self) -> list[str]:
        return sorted(zeile.tag for zeile in self.tag_zeilen)

    @property
    def aktiv_phasen(self) -> list[dict]:
        """Alle aktiv-Phasen aus der Tag-Historie, lokale Zeit: [{von, bis}].
        bis=None heißt läuft noch. Erledigt beendet die offene Phase mit erledigt_am.
        Der Zeitstrahl zeichnet jede Phase als eigenen Balken."""
        phasen: list[dict] = []
        von: datetime | None = None
        for event in self.historie:
            if event.tag != "aktiv":
                continue
            if event.aktion == "gesetzt" and von is None:
                von = _lokal(event.zeitpunkt)
            elif event.aktion == "entfernt" and von is not None:
                phasen.append({"von": von, "bis": _lokal(event.zeitpunkt)})
                von = None
        if von is not None:
            bis = _lokal(self.erledigt_am) if self.erledigt_am is not None else None
            phasen.append({"von": von, "bis": bis})
        return phasen

    @property
    def aktiv_seit(self) -> datetime | None:
        """Wann das aktuelle `aktiv`-Tag gesetzt wurde, als lokale Zeit (für die Tagesleiste)."""
        if "aktiv" not in self.tags:
            return None
        phasen = self.aktiv_phasen
        if phasen and phasen[-1]["bis"] is None:
            return phasen[-1]["von"]
        return None


class TaskTag(Base):
    __tablename__ = "task_tags"

    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String(50), primary_key=True)


class TagEvent(Base):
    """Tag-Historie: wann kam welches Tag auf einen Task, wann ging es runter."""

    __tablename__ = "tag_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    tag: Mapped[str] = mapped_column(String(50))
    aktion: Mapped[str] = mapped_column(String(10))  # gesetzt | entfernt
    zeitpunkt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TimeBlock(Base):
    """Meetings und andere Blocker mit fixem Zeitraum."""

    __tablename__ = "time_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    titel: Mapped[str] = mapped_column(String(300))
    typ: Mapped[str] = mapped_column(String(20))  # meeting | blocker
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ende: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WorkSchedule(Base):
    """Arbeitszeit-Modell, genau eine Zeile.

    modus "stunden": nur stunden_pro_tag zählt (Lage egal).
    modus "feste_zeiten": zeiten hält pro Wochentag ["HH:MM", "HH:MM"] oder null (frei).
    """

    __tablename__ = "work_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    modus: Mapped[str] = mapped_column(String(20), default="stunden")
    stunden_pro_tag: Mapped[float] = mapped_column(Float, default=8.0)
    # {"mo": ["08:00", "16:30"], ..., "sa": null, "so": null}
    zeiten: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
