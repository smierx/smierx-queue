from datetime import date, datetime, timedelta, timezone

from sqlalchemy import (
    JSON,
    Date,
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

# Zwei komplette Welten in einer App: Tasks, Blocker und Arbeitszeit-Modell
# gelten je Bereich, der Schalter im Frontend wechselt alles auf einmal.
BEREICHE = {"arbeit", "privat"}


def _lokal(zeitpunkt: datetime) -> datetime:
    """DB-Defaults sind UTC (SQLite naiv, Postgres aware) → lokale, naive Zeit,
    konsistent zu den TimeBlocks."""
    if zeitpunkt.tzinfo is None:
        zeitpunkt = zeitpunkt.replace(tzinfo=timezone.utc)
    return zeitpunkt.astimezone().replace(tzinfo=None)


def _phasenzeit(zeitpunkt: datetime) -> datetime:
    """TaskPhase-Zeiten schreibt die App Python-seitig als lokale naive Zeit.
    Postgres hängt beim Lesen nur ein Session-TZ-Label an, der Wert selbst bleibt
    wie geschrieben → Label abstreifen, nie konvertieren (wie _ohne_tz bei den
    TimeBlocks). SQLite gibt sie naiv zurück."""
    return zeitpunkt.replace(tzinfo=None)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    titel: Mapped[str] = mapped_column(String(300))
    beschreibung: Mapped[str] = mapped_column(Text, default="")
    bereich: Mapped[str] = mapped_column(
        String(10), index=True, default="arbeit", server_default="arbeit"
    )
    # Der Tag, auf dem der Task in der Queue liegt. Invariante: jeder offene Task
    # liegt auf genau einem Tag >= heute, der Rollover räumt die Vergangenheit.
    geplant_am: Mapped[date] = mapped_column(Date, index=True, default=date.today)
    # Queue-Reihenfolge innerhalb eines Tages und Bereichs, klein = weiter oben.
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
    phasen: Mapped[list["TaskPhase"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="TaskPhase.von"
    )

    @property
    def tags(self) -> list[str]:
        return sorted(zeile.tag for zeile in self.tag_zeilen)

    @property
    def aktiv_phasen(self) -> list[dict]:
        """Alle aktiv-Phasen als lokale Zeit: [{id, von, bis}]. bis=None heißt läuft
        noch. Der Zeitstrahl zeichnet jede Phase als eigenen Balken, die Id
        braucht das Nachtragen (PATCH/DELETE /phasen/{id})."""
        return [
            {
                "id": p.id,
                "von": _phasenzeit(p.von),
                "bis": _phasenzeit(p.bis) if p.bis is not None else None,
            }
            for p in self.phasen
        ]

    @property
    def aktiv_seit(self) -> datetime | None:
        """Wann das aktuelle `aktiv`-Tag gesetzt wurde, als lokale Zeit (für die Tagesleiste)."""
        if "aktiv" not in self.tags:
            return None
        offene = [p for p in self.phasen if p.bis is None]
        return _phasenzeit(offene[-1].von) if offene else None

    @property
    def gesamt_minuten(self) -> int:
        """Summe aller Phasen über alle Tage, offene zählen bis jetzt.
        Die Zeiterfassung für den Projekt-Modus."""
        jetzt = datetime.now()
        summe = sum(
            (
                ((_phasenzeit(p.bis) if p.bis is not None else jetzt) - _phasenzeit(p.von))
                for p in self.phasen
            ),
            timedelta(0),
        )
        return max(0, round(summe.total_seconds() / 60))


class TaskTag(Base):
    __tablename__ = "task_tags"

    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String(50), primary_key=True)


class TaskPhase(Base):
    """Eine aktiv-Phase: von wann bis wann ein Task lief. bis=NULL heißt läuft noch.

    Die Tag-Logik schreibt Phasen direkt (aktiv setzen öffnet, entfernen schließt),
    fürs Nachtragen sind sie per CRUD editierbar. Invariante: ein Task hat genau
    dann eine offene Phase, wenn er das aktiv-Tag trägt."""

    __tablename__ = "task_phases"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    von: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    bis: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    bereich: Mapped[str] = mapped_column(
        String(10), index=True, default="arbeit", server_default="arbeit"
    )
    titel: Mapped[str] = mapped_column(String(300))
    typ: Mapped[str] = mapped_column(String(20))  # meeting | blocker
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ende: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WorkSchedule(Base):
    """Arbeitszeit-Modell, genau eine Zeile pro Bereich.

    modus "stunden": nur stunden_pro_tag zählt (Lage egal).
    modus "feste_zeiten": zeiten hält pro Wochentag ["HH:MM", "HH:MM"] oder null (frei).
    """

    __tablename__ = "work_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    bereich: Mapped[str] = mapped_column(
        String(10), unique=True, default="arbeit", server_default="arbeit"
    )
    modus: Mapped[str] = mapped_column(String(20), default="stunden")
    stunden_pro_tag: Mapped[float] = mapped_column(Float, default=8.0)
    # {"mo": ["08:00", "16:30"], ..., "sa": null, "so": null}
    zeiten: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
