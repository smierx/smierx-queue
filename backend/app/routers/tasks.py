import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    VALID_TAGS,
    ZUSTAND_TAGS,
    TagEvent,
    Task,
    TaskPhase,
    TaskTag,
    TimeBlock,
)
from app.rollover import rollover_ausfuehren
from app.schemas import (
    Bereich,
    ErledigtDaten,
    QueueOrder,
    TagEventOut,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)

router = APIRouter(tags=["tasks"])
logger = logging.getLogger("smierx_queue.tasks")


def _jetzt_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc_naiv(lokal: datetime) -> datetime:
    """Lokale (naive) Zeit → UTC-naiv, wie _jetzt_utc sie speichert."""
    return lokal.astimezone(timezone.utc).replace(tzinfo=None)


def _tages_ende_position(db: Session, tag: date, bereich: str) -> int:
    max_position = db.scalar(
        select(func.max(Task.position)).where(
            Task.erledigt_am.is_(None), Task.geplant_am == tag, Task.bereich == bereich
        )
    )
    return (max_position or 0) + 1


def _task_holen(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} nicht gefunden")
    return task


def _tag_pruefen(tag: str) -> str:
    if tag not in VALID_TAGS:
        raise HTTPException(422, f"Unbekanntes Tag {tag!r}. Gültig sind: {sorted(VALID_TAGS)}")
    return tag


def _offene_phase_schliessen(task: Task, zeitpunkt: datetime) -> None:
    for phase in task.phasen:
        if phase.bis is None:
            phase.bis = zeitpunkt


def _tag_anwenden(task: Task, tag: str) -> None:
    """Tag setzen inkl. Historie. Zustand-Tags verdrängen sich gegenseitig.
    Führt die Phasen mit: aktiv setzen öffnet eine, aktiv verlieren schließt sie."""
    jetzt = datetime.now()  # lokale Zeit, Konvention der TaskPhase-Spalten
    if tag in ZUSTAND_TAGS:
        for zeile in [z for z in task.tag_zeilen if z.tag in ZUSTAND_TAGS and z.tag != tag]:
            task.tag_zeilen.remove(zeile)
            task.historie.append(TagEvent(tag=zeile.tag, aktion="entfernt"))
            if zeile.tag == "aktiv":
                _offene_phase_schliessen(task, jetzt)
    if tag not in task.tags:
        task.tag_zeilen.append(TaskTag(tag=tag))
        task.historie.append(TagEvent(tag=tag, aktion="gesetzt"))
        if tag == "aktiv":
            task.phasen.append(TaskPhase(von=jetzt))


@router.get("/tasks", response_model=list[TaskOut])
def tasks_auflisten(
    datum: date | None = None,
    tag: str | None = None,
    erledigt: bool = False,
    bereich: Bereich = "arbeit",
    db: Session = Depends(get_db),
) -> list[Task]:
    """Offene Tasks eines Tages und Bereichs (Default heute/arbeit), das Archiv
    (erledigt=true) gilt pro Bereich und über alle Tage."""
    stmt = select(Task).where(Task.bereich == bereich)
    if erledigt:
        stmt = stmt.where(Task.erledigt_am.is_not(None)).order_by(Task.erledigt_am.desc())
    else:
        ziel = datum or date.today()
        if ziel == date.today():
            rollover_ausfuehren(db)
        stmt = (
            stmt.where(Task.erledigt_am.is_(None), Task.geplant_am == ziel)
            .order_by(Task.position)
        )
    if tag is not None:
        _tag_pruefen(tag)
        stmt = stmt.join(TaskTag).where(TaskTag.tag == tag)
    return list(db.scalars(stmt))


@router.post("/tasks", response_model=TaskOut, status_code=201)
def task_anlegen(
    daten: TaskCreate,
    db: Session = Depends(get_db),
) -> Task:
    geplant_am = daten.geplant_am or date.today()
    task = Task(
        titel=daten.titel,
        beschreibung=daten.beschreibung,
        bereich=daten.bereich,
        geplant_am=geplant_am,
        position=_tages_ende_position(db, geplant_am, daten.bereich),
        dauer_minuten=daten.dauer_minuten,
    )
    task.tag_zeilen = [TaskTag(tag=t) for t in daten.tags]
    task.historie = [TagEvent(tag=t, aktion="gesetzt") for t in daten.tags]
    if "aktiv" in daten.tags:
        task.phasen = [TaskPhase(von=datetime.now())]
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("/tasks/{task_id}", response_model=TaskOut)
def task_lesen(task_id: int, db: Session = Depends(get_db)) -> Task:
    return _task_holen(db, task_id)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def task_aendern(
    task_id: int,
    daten: TaskUpdate,
    db: Session = Depends(get_db),
) -> Task:
    task = _task_holen(db, task_id)
    if daten.titel is not None:
        task.titel = daten.titel
    if daten.beschreibung is not None:
        task.beschreibung = daten.beschreibung
    if daten.dauer_minuten is not None:
        task.dauer_minuten = daten.dauer_minuten
    # Tag- und/oder Bereichswechsel: eine Neupositionierung ans Ende der Ziel-Queue.
    ziel_tag = daten.geplant_am if daten.geplant_am is not None else task.geplant_am
    ziel_bereich = daten.bereich if daten.bereich is not None else task.bereich
    if (ziel_tag, ziel_bereich) != (task.geplant_am, task.bereich):
        task.geplant_am = ziel_tag
        task.bereich = ziel_bereich
        task.position = _tages_ende_position(db, ziel_tag, ziel_bereich)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/tasks/{task_id}", status_code=204)
def task_loeschen(task_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(_task_holen(db, task_id))
    db.commit()


@router.put("/tasks/{task_id}/tags/{tag}", response_model=TaskOut)
def tag_setzen(
    task_id: int,
    tag: str,
    db: Session = Depends(get_db),
) -> Task:
    task = _task_holen(db, task_id)
    _tag_pruefen(tag)
    if tag not in task.tags:
        _tag_anwenden(task, tag)
        db.commit()
        db.refresh(task)
    return task


@router.delete("/tasks/{task_id}/tags/{tag}", response_model=TaskOut)
def tag_entfernen(
    task_id: int,
    tag: str,
    db: Session = Depends(get_db),
) -> Task:
    task = _task_holen(db, task_id)
    _tag_pruefen(tag)
    zeile = next((z for z in task.tag_zeilen if z.tag == tag), None)
    if zeile is not None:
        task.tag_zeilen.remove(zeile)
        task.historie.append(TagEvent(tag=tag, aktion="entfernt"))
        if tag == "aktiv":
            _offene_phase_schliessen(task, datetime.now())
        db.commit()
        db.refresh(task)
    return task


@router.post("/tasks/{task_id}/erledigt", response_model=TaskOut)
def task_erledigen(
    task_id: int,
    daten: ErledigtDaten | None = None,
    db: Session = Depends(get_db),
) -> Task:
    """Task ins Archiv statt löschen. Läuft er gerade, endet die Phase
    und das aktiv-Tag geht runter (Wiederöffnen startet ihn nicht von selbst).
    Ein Zeitpunkt im Body datiert das Erledigen fürs Nachtragen zurück; hat der
    Task dann noch keine Phasen, entsteht eine über die geplante Dauer, damit
    er im Zeitstrahl und im Export sichtbar ist."""
    task = _task_holen(db, task_id)
    if task.erledigt_am is None:
        zeitpunkt = daten.zeitpunkt if daten and daten.zeitpunkt else datetime.now()
        if zeitpunkt.tzinfo is not None:  # API-Input normalisieren, Konvention ist lokal naiv
            zeitpunkt = zeitpunkt.astimezone().replace(tzinfo=None)
        task.erledigt_am = _utc_naiv(zeitpunkt)
        if daten and daten.zeitpunkt and not task.phasen:
            task.phasen.append(
                TaskPhase(von=zeitpunkt - timedelta(minutes=task.dauer_minuten), bis=zeitpunkt)
            )
        _offene_phase_schliessen(task, zeitpunkt)
        zeile = next((z for z in task.tag_zeilen if z.tag == "aktiv"), None)
        if zeile is not None:
            task.tag_zeilen.remove(zeile)
            task.historie.append(TagEvent(tag="aktiv", aktion="entfernt"))
        db.commit()
        db.refresh(task)
    return task


@router.delete("/tasks/{task_id}/erledigt", response_model=TaskOut)
def task_wieder_oeffnen(task_id: int, db: Session = Depends(get_db)) -> Task:
    task = _task_holen(db, task_id)
    if task.erledigt_am is not None:
        task.erledigt_am = None
        task.geplant_am = date.today()
        # hinten in der Queue des eigenen Bereichs einreihen
        task.position = _tages_ende_position(db, task.geplant_am, task.bereich)
        db.commit()
        db.refresh(task)
    return task


@router.get("/tasks/{task_id}/historie", response_model=list[TagEventOut])
def historie_lesen(task_id: int, db: Session = Depends(get_db)) -> list[TagEvent]:
    return _task_holen(db, task_id).historie


def _fenster_zusammenfassen(bloecke: list[TimeBlock]) -> list[tuple[datetime, datetime]]:
    """Blocker/Meetings als sortierte, überlappungsfreie Zeitfenster (naive
    lokale Zeit, damit Vergleiche mit datetime.now() gehen). Nutzt der Export."""
    fenster: list[tuple[datetime, datetime]] = []
    for start, ende in sorted(
        (b.start.replace(tzinfo=None), b.ende.replace(tzinfo=None)) for b in bloecke
    ):
        if fenster and start <= fenster[-1][1]:
            fenster[-1] = (fenster[-1][0], max(fenster[-1][1], ende))
        else:
            fenster.append((start, ende))
    return fenster


@router.post("/queue/tick", response_model=list[TaskOut])
def queue_tick(bereich: Bereich = "arbeit", db: Session = Depends(get_db)) -> list[Task]:
    """Rollover fahren und die heutige Liste des angefragten Bereichs
    zurückgeben. Es gibt bewusst keinen automatischen Statuswechsel mehr:
    die Dauer ist eine Schätzung, überzogene Tasks laufen einfach weiter,
    gewechselt wird von Hand (Entscheid 2026-07-28)."""
    rollover_ausfuehren(db)
    return list(
        db.scalars(
            select(Task)
            .where(
                Task.erledigt_am.is_(None),
                Task.geplant_am == date.today(),
                Task.bereich == bereich,
            )
            .order_by(Task.position)
        )
    )


@router.post("/queue/feierabend", response_model=list[TaskOut])
def feierabend(bereich: Bereich = "arbeit", db: Session = Depends(get_db)) -> list[Task]:
    """Feierabend im Bereich: alle aktiven Tasks wandern auf next, ihre Phasen
    enden. Der automatische Statuswechsel bleibt danach still, bis wieder etwas
    aktiv ist. Der andere Bereich läuft unberührt weiter."""
    tasks = list(
        db.scalars(
            select(Task)
            .where(
                Task.erledigt_am.is_(None),
                Task.geplant_am == date.today(),
                Task.bereich == bereich,
            )
            .order_by(Task.position)
        )
    )
    for task in tasks:
        if "aktiv" in task.tags:
            _tag_anwenden(task, "next")
    db.commit()
    return tasks


@router.put("/queue/order", response_model=list[TaskOut])
def queue_umsortieren(
    daten: QueueOrder,
    db: Session = Depends(get_db),
) -> list[Task]:
    """Nimmt die komplette Ziel-Reihenfolge eines Tages und Bereichs entgegen
    (wie nach dem Drag & Drop), Default heute/arbeit."""
    ziel = daten.datum or date.today()
    tasks = {
        t.id: t
        for t in db.scalars(
            select(Task).where(
                Task.erledigt_am.is_(None),
                Task.geplant_am == ziel,
                Task.bereich == daten.bereich,
            )
        )
    }
    if set(daten.task_ids) != set(tasks) or len(daten.task_ids) != len(tasks):
        raise HTTPException(
            422,
            "task_ids muss jede offene Task-Id des Tages und Bereichs genau einmal enthalten",
        )
    for position, task_id in enumerate(daten.task_ids, start=1):
        tasks[task_id].position = position
    db.commit()
    return sorted(tasks.values(), key=lambda t: t.position)
