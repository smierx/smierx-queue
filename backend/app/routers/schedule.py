from datetime import date, datetime, time

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import aktueller_user
from app.database import get_db
from app.models import TimeBlock, WorkSchedule
from app.schemas import WOCHENTAGE, CapacityOut, ScheduleOut, ScheduleUpdate, _minuten

router = APIRouter(tags=["schedule"])


def _schedule_holen(db: Session, user: str) -> WorkSchedule:
    """Eine Zeile pro User, lazily angelegt."""
    schedule = db.scalar(select(WorkSchedule).where(WorkSchedule.user_id == user))
    if schedule is None:
        schedule = WorkSchedule(user_id=user)
        db.add(schedule)
        try:
            db.commit()
            db.refresh(schedule)
        except IntegrityError:
            # Beim ersten Seitenaufruf legen /schedule und /capacity parallel an,
            # der Verlierer des Race liest einfach die Zeile des Gewinners.
            db.rollback()
            schedule = db.scalar(select(WorkSchedule).where(WorkSchedule.user_id == user))
    return schedule


@router.get("/schedule", response_model=ScheduleOut)
def schedule_lesen(
    db: Session = Depends(get_db), user: str = Depends(aktueller_user)
) -> WorkSchedule:
    return _schedule_holen(db, user)


@router.put("/schedule", response_model=ScheduleOut)
def schedule_setzen(
    daten: ScheduleUpdate,
    db: Session = Depends(get_db),
    user: str = Depends(aktueller_user),
) -> WorkSchedule:
    schedule = _schedule_holen(db, user)
    schedule.modus = daten.modus
    schedule.stunden_pro_tag = daten.stunden_pro_tag
    schedule.zeiten = daten.zeiten
    db.commit()
    db.refresh(schedule)
    return schedule


def _ohne_tz(wert: datetime) -> datetime:
    # Vereinfachung für den Start: alles als lokale, naive Zeit behandeln.
    # Saubere Zeitzonen-Behandlung kommt mit dem Kalender-Import.
    return wert.replace(tzinfo=None)


def _intervalle_mergen(
    intervalle: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """Überlappende Blöcke zusammenfassen, damit nichts doppelt zählt."""
    gemergt: list[tuple[datetime, datetime]] = []
    for start, ende in sorted(intervalle):
        if gemergt and start <= gemergt[-1][1]:
            gemergt[-1] = (gemergt[-1][0], max(gemergt[-1][1], ende))
        else:
            gemergt.append((start, ende))
    return gemergt


@router.get("/capacity", response_model=CapacityOut)
def kapazitaet(
    datum: date | None = None,
    db: Session = Depends(get_db),
    user: str = Depends(aktueller_user),
) -> CapacityOut:
    """Freie Kapazität eines Tages: Arbeitszeit minus Termine/Blocker."""
    tag = datum or date.today()
    schedule = _schedule_holen(db, user)

    tag_start = datetime.combine(tag, time.min)
    tag_ende = datetime.combine(tag, time.max)

    # Rahmen aus dem Arbeitszeit-Modell.
    fenster = None
    if schedule.modus == "feste_zeiten":
        fenster = (schedule.zeiten or {}).get(WOCHENTAGE[tag.weekday()])
        if fenster is None:
            fenster_start, fenster_ende = tag_start, tag_start  # freier Tag
        else:
            fenster_start = datetime.combine(tag, time(*divmod(_minuten(fenster[0]), 60)))
            fenster_ende = datetime.combine(tag, time(*divmod(_minuten(fenster[1]), 60)))
        arbeitszeit = int((fenster_ende - fenster_start).total_seconds() // 60)
    else:
        # Stunden-Modus: Lage egal, Blöcke des Tages werden voll abgezogen.
        fenster_start, fenster_ende = tag_start, tag_ende
        arbeitszeit = int(schedule.stunden_pro_tag * 60)

    bloecke = list(
        db.scalars(
            select(TimeBlock)
            .where(
                TimeBlock.user_id == user,
                TimeBlock.ende > tag_start,
                TimeBlock.start < tag_ende,
            )
            .order_by(TimeBlock.start)
        )
    )

    intervalle = []
    for block in bloecke:
        start = max(_ohne_tz(block.start), fenster_start)
        ende = min(_ohne_tz(block.ende), fenster_ende)
        if ende > start:
            intervalle.append((start, ende))

    geblockt = sum(
        int((ende - start).total_seconds() // 60)
        for start, ende in _intervalle_mergen(intervalle)
    )

    return CapacityOut(
        datum=tag.isoformat(),
        modus=schedule.modus,
        arbeitszeit_minuten=arbeitszeit,
        geblockt_minuten=geblockt,
        frei_minuten=max(0, arbeitszeit - geblockt),
        fenster_von=fenster[0] if fenster else None,
        fenster_bis=fenster[1] if fenster else None,
        bloecke=bloecke,
    )
