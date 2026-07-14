from datetime import datetime

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
    "support",
    "discussion",
    "critical",
}

TIMEBLOCK_TYPEN = {"meeting", "blocker"}
SCHEDULE_MODI = {"stunden", "feste_zeiten"}


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Keycloak-`sub`, im Dev-Modus "dev". Jeder sieht nur seine Zeilen.
    user_id: Mapped[str] = mapped_column(String(100), index=True, default="dev")
    titel: Mapped[str] = mapped_column(String(300))
    beschreibung: Mapped[str] = mapped_column(Text, default="")
    # Queue-Reihenfolge pro User, klein = weiter oben. Reorder schreibt die Positionen neu.
    position: Mapped[int] = mapped_column(Integer, index=True)
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
    user_id: Mapped[str] = mapped_column(String(100), index=True, default="dev")
    titel: Mapped[str] = mapped_column(String(300))
    typ: Mapped[str] = mapped_column(String(20))  # meeting | blocker
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ende: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WorkSchedule(Base):
    """Arbeitszeit-Modell, eine Zeile pro User.

    modus "stunden": nur stunden_pro_tag zählt (Lage egal).
    modus "feste_zeiten": zeiten hält pro Wochentag ["HH:MM", "HH:MM"] oder null (frei).
    """

    __tablename__ = "work_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), unique=True, default="dev")
    modus: Mapped[str] = mapped_column(String(20), default="stunden")
    stunden_pro_tag: Mapped[float] = mapped_column(Float, default=8.0)
    # {"mo": ["08:00", "16:30"], ..., "sa": null, "so": null}
    zeiten: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
