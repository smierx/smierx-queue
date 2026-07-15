import re
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import aktueller_user
from app.database import get_db
from app.models import Task, TimeBlock, _lokal
from app.routers.tasks import _fenster_zusammenfassen
from app.schemas import ExportBlock, ExportErledigt, ExportOut, ExportPhase, ExportSummary

router = APIRouter(tags=["export"])

WOCHE_MUSTER = re.compile(r"^(\d{4})-W(\d{2})$")


def _wochen_fenster(woche: str | None) -> tuple[str, datetime, datetime]:
    """Kalenderwoche als [Montag 00:00, Montag der Folgewoche), lokale Zeit."""
    if woche is None:
        iso = date.today().isocalendar()
        woche = f"{iso.year}-W{iso.week:02d}"
    treffer = WOCHE_MUSTER.match(woche)
    if treffer is None:
        raise HTTPException(422, "woche muss das Format JJJJ-WXX haben, z.B. 2026-W29")
    try:
        montag = date.fromisocalendar(int(treffer.group(1)), int(treffer.group(2)), 1)
    except ValueError:
        raise HTTPException(422, f"{woche} ist keine gültige Kalenderwoche") from None
    start = datetime(montag.year, montag.month, montag.day)
    return woche, start, start + timedelta(days=7)


def _ueberlappung(
    von: datetime, bis: datetime, fenster: list[tuple[datetime, datetime]]
) -> timedelta:
    """Wie viel von [von, bis) in Blocker-Fenstern liegt."""
    summe = timedelta(0)
    for f_von, f_bis in fenster:
        schnitt = min(bis, f_bis) - max(von, f_von)
        if schnitt > timedelta(0):
            summe += schnitt
    return summe


def _minuten(delta: timedelta) -> int:
    return round(delta.total_seconds() / 60)


@router.get("/export", response_model=ExportOut)
def export_woche(
    woche: str | None = None,
    db: Session = Depends(get_db),
    user: str = Depends(aktueller_user),
) -> ExportOut:
    """Wochen-Export als JSON: alle aktiv-Phasen (Arbeitszeit abzüglich Blocker),
    erledigte Tasks und Blocker der Woche. Ohne Parameter die aktuelle Woche."""
    woche, start, ende = _wochen_fenster(woche)
    jetzt = datetime.now()

    tasks = list(db.scalars(select(Task).where(Task.user_id == user)))
    bloecke = list(db.scalars(select(TimeBlock).where(TimeBlock.user_id == user)))
    fenster = _fenster_zusammenfassen(bloecke)

    phasen: list[ExportPhase] = []
    for task in tasks:
        for phase in task.aktiv_phasen:
            offen = phase["bis"] is None
            von = max(phase["von"], start)
            bis = min(phase["bis"] if not offen else jetzt, ende)
            if bis <= von:
                continue  # Phase liegt außerhalb der Woche
            netto = (bis - von) - _ueberlappung(von, bis, fenster)
            phasen.append(
                ExportPhase(
                    task_id=task.id, titel=task.titel, tags=task.tags,
                    von=von, bis=bis, minuten=_minuten(netto), offen=offen,
                )
            )
    phasen.sort(key=lambda p: p.von)

    erledigt = sorted(
        (
            ExportErledigt(
                task_id=t.id, titel=t.titel,
                erledigt_am=_lokal(t.erledigt_am), dauer_minuten=t.dauer_minuten,
            )
            for t in tasks
            if t.erledigt_am is not None and start <= _lokal(t.erledigt_am) < ende
        ),
        key=lambda e: e.erledigt_am,
    )

    wochen_bloecke = sorted(
        (
            ExportBlock(
                titel=b.titel, typ=b.typ, start=b.start, ende=b.ende,
                minuten=_minuten(min(b.ende, ende) - max(b.start, start)),
            )
            for b in bloecke
            if b.ende > start and b.start < ende
        ),
        key=lambda b: b.start,
    )

    return ExportOut(
        woche=woche, von=start, bis=ende, erstellt_am=jetzt,
        phasen=phasen, erledigt=erledigt, bloecke=wochen_bloecke,
        zusammenfassung=ExportSummary(
            gearbeitet_minuten=sum(p.minuten for p in phasen),
            geblockt_minuten=sum(b.minuten for b in wochen_bloecke),
            erledigte_tasks=len(erledigt),
        ),
    )
