"""Phasen lesen und nachtragen.

GET /phasen?datum= füttert die Timeline eines Tages und sieht auch Phasen von
Tasks, die inzwischen auf anderen Tagen oder im Archiv liegen. Der Rest ist
CRUD fürs Nachtragen. Invariante zum Tag-System: eine offene Phase gehört zu
einem aktiv-Task; wer sie schließt oder löscht, nimmt das aktiv-Tag mit runter.
"""

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Task, TaskPhase, _phasenzeit
from app.routers.tasks import _tag_anwenden, _task_holen
from app.schemas import Bereich, PhaseCreate, PhaseOut, PhaseUpdate, TagesPhaseOut

router = APIRouter(tags=["phasen"])


def _phase_holen(db: Session, phase_id: int) -> TaskPhase:
    phase = db.get(TaskPhase, phase_id)
    if phase is None:
        raise HTTPException(404, f"Phase {phase_id} nicht gefunden")
    return phase


def _ueberlappung_pruefen(
    task: Task, von: datetime, bis: datetime, ausser_id: int | None = None
) -> None:
    """Phasen desselben Tasks dürfen sich nicht überlappen, offene zählen bis jetzt."""
    for phase in task.phasen:
        if phase.id == ausser_id:
            continue
        p_von = _phasenzeit(phase.von)
        p_bis = _phasenzeit(phase.bis) if phase.bis is not None else datetime.now()
        if von < p_bis and p_von < bis:
            raise HTTPException(
                422, f"Zeitraum überlappt mit einer bestehenden Phase ({p_von} bis {p_bis})"
            )


def _aktiv_beenden(db: Session, task: Task) -> None:
    """Tag-Seite der Invariante: ohne offene Phase kein aktiv-Tag."""
    if "aktiv" in task.tags:
        _tag_anwenden(task, "next")


@router.get("/phasen", response_model=list[TagesPhaseOut])
def phasen_eines_tages(
    datum: date | None = None,
    bereich: Bereich = "arbeit",
    db: Session = Depends(get_db),
) -> list[TagesPhaseOut]:
    tag = datum or date.today()
    tag_start = datetime.combine(tag, time.min)
    tag_ende = tag_start + timedelta(days=1)
    zeilen = db.execute(
        select(TaskPhase, Task)
        .join(Task)
        .where(Task.bereich == bereich)
        .order_by(TaskPhase.von)
    ).all()
    ergebnis = []
    for phase, task in zeilen:
        von = _phasenzeit(phase.von)
        bis = _phasenzeit(phase.bis) if phase.bis is not None else None
        if von >= tag_ende or (bis is not None and bis <= tag_start):
            continue
        ergebnis.append(
            TagesPhaseOut(
                id=phase.id, task_id=task.id, titel=task.titel, tags=task.tags,
                von=von, bis=bis,
            )
        )
    return ergebnis


@router.post("/tasks/{task_id}/phasen", response_model=PhaseOut, status_code=201)
def phase_nachtragen(
    task_id: int,
    daten: PhaseCreate,
    db: Session = Depends(get_db),
) -> TaskPhase:
    task = _task_holen(db, task_id)
    _ueberlappung_pruefen(task, daten.von, daten.bis)
    phase = TaskPhase(von=daten.von, bis=daten.bis)
    task.phasen.append(phase)
    db.commit()
    db.refresh(phase)
    return phase


@router.patch("/phasen/{phase_id}", response_model=PhaseOut)
def phase_aendern(
    phase_id: int,
    daten: PhaseUpdate,
    db: Session = Depends(get_db),
) -> TaskPhase:
    phase = _phase_holen(db, phase_id)
    task = db.get(Task, phase.task_id)
    war_offen = phase.bis is None

    von = daten.von if daten.von is not None else _phasenzeit(phase.von)
    if daten.bis is not None:
        bis = daten.bis
    else:
        bis = _phasenzeit(phase.bis) if phase.bis is not None else None
    if bis is not None and bis <= von:
        raise HTTPException(422, "bis muss nach von liegen")
    _ueberlappung_pruefen(task, von, bis if bis is not None else datetime.now(), phase.id)

    phase.von = von
    phase.bis = bis
    if war_offen and bis is not None:
        _aktiv_beenden(db, task)
    db.commit()
    db.refresh(phase)
    return phase


@router.delete("/phasen/{phase_id}", status_code=204)
def phase_loeschen(phase_id: int, db: Session = Depends(get_db)) -> None:
    phase = _phase_holen(db, phase_id)
    task = db.get(Task, phase.task_id)
    war_offen = phase.bis is None
    task.phasen.remove(phase)
    if war_offen:
        _aktiv_beenden(db, task)
    db.commit()
