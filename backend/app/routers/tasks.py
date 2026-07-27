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
from app.schemas import ErledigtDaten, QueueOrder, TagEventOut, TaskCreate, TaskOut, TaskUpdate

router = APIRouter(tags=["tasks"])
logger = logging.getLogger("smierx_queue.tasks")


def _jetzt_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc_naiv(lokal: datetime) -> datetime:
    """Lokale (naive) Zeit → UTC-naiv, wie _jetzt_utc sie speichert."""
    return lokal.astimezone(timezone.utc).replace(tzinfo=None)


def _tages_ende_position(db: Session, tag: date) -> int:
    max_position = db.scalar(
        select(func.max(Task.position)).where(
            Task.erledigt_am.is_(None), Task.geplant_am == tag
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
    db: Session = Depends(get_db),
) -> list[Task]:
    """Offene Tasks eines Tages (Default heute), das Archiv (erledigt=true) ist global."""
    stmt = select(Task)
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
        geplant_am=geplant_am,
        position=_tages_ende_position(db, geplant_am),
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
    if daten.geplant_am is not None and daten.geplant_am != task.geplant_am:
        task.geplant_am = daten.geplant_am
        task.position = _tages_ende_position(db, daten.geplant_am)
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
    Ein Zeitpunkt im Body datiert das Erledigen fürs Nachtragen zurück."""
    task = _task_holen(db, task_id)
    if task.erledigt_am is None:
        zeitpunkt = daten.zeitpunkt if daten and daten.zeitpunkt else datetime.now()
        task.erledigt_am = _utc_naiv(zeitpunkt)
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
        task.position = _tages_ende_position(db, task.geplant_am)  # hinten einreihen
        db.commit()
        db.refresh(task)
    return task


@router.get("/tasks/{task_id}/historie", response_model=list[TagEventOut])
def historie_lesen(task_id: int, db: Session = Depends(get_db)) -> list[TagEvent]:
    return _task_holen(db, task_id).historie


# Geparkte Tasks überspringt der automatische Statuswechsel.
GEPARKT = {"pausiert", "holding", "inaktiv"}


def _fenster_zusammenfassen(bloecke: list[TimeBlock]) -> list[tuple[datetime, datetime]]:
    """Blocker/Meetings als sortierte, überlappungsfreie Zeitfenster (naive
    lokale Zeit, damit Vergleiche mit datetime.now() und aktiv_seit gehen)."""
    fenster: list[tuple[datetime, datetime]] = []
    for start, ende in sorted(
        (b.start.replace(tzinfo=None), b.ende.replace(tzinfo=None)) for b in bloecke
    ):
        if fenster and start <= fenster[-1][1]:
            fenster[-1] = (fenster[-1][0], max(fenster[-1][1], ende))
        else:
            fenster.append((start, ende))
    return fenster


def _geplantes_ende(
    start: datetime, dauer_minuten: int, fenster: list[tuple[datetime, datetime]]
) -> datetime:
    """Geplantes Ende eines Tasks: Dauer ab Start, Blocker-Fenster zählen nicht
    als Arbeitszeit und schieben das Ende nach hinten."""
    cursor = start
    rest = timedelta(minutes=dauer_minuten)
    for von, bis in fenster:
        if bis <= cursor:
            continue
        frei = von - cursor
        if frei >= rest:
            return cursor + rest
        if frei > timedelta(0):
            rest -= frei
        cursor = bis
    return cursor + rest


def uebergabe_pruefen(db: Session) -> Task | None:
    """Automatischer Statuswechsel als Übergabe: sind Tasks aktiv, aber keiner mehr
    in seiner geplanten Zeit (aktiv seit + Dauer, Blocker schieben das Ende nach
    hinten), wird der nächste Queue-Task aktiv. Läuft gar nichts (z.B. nach
    Feierabend), passiert nichts. Mitten in einem Blocker passiert nichts.
    Höchstens ein Wechsel pro Aufruf, geparkte Tasks (pausiert, holding, inaktiv)
    bleiben liegen. Betrachtet nur die heutige Queue, vorgeplante Tage fasst der
    Tick nie an. Committet selbst, gibt den aktivierten Task zurück."""
    tasks = list(
        db.scalars(
            select(Task)
            .where(Task.erledigt_am.is_(None), Task.geplant_am == date.today())
            .order_by(Task.position)
        )
    )
    jetzt = datetime.now()  # lokale Zeit, konsistent zu aktiv_seit und TimeBlocks
    fenster = _fenster_zusammenfassen(list(db.scalars(select(TimeBlock))))
    im_blocker = any(von <= jetzt < bis for von, bis in fenster)
    aktive = [t for t in tasks if "aktiv" in t.tags]
    laeuft_noch = any(
        t.aktiv_seit is not None
        and _geplantes_ende(t.aktiv_seit, t.dauer_minuten, fenster) > jetzt
        for t in aktive
    )
    if not aktive or laeuft_noch or im_blocker:
        return None
    wartende = sorted(
        (t for t in tasks if "aktiv" not in t.tags and not GEPARKT & set(t.tags)),
        key=lambda t: (0 if "next" in t.tags else 1, t.position),
    )
    if not wartende:
        return None
    naechster = wartende[0]
    _tag_anwenden(naechster, "aktiv")
    db.commit()
    logger.info("Auto-aktiviert: Task %s (%s)", naechster.id, naechster.titel)
    return naechster


@router.post("/queue/tick", response_model=list[TaskOut])
def queue_tick(db: Session = Depends(get_db)) -> list[Task]:
    """Rollover fahren, Übergabe prüfen (siehe uebergabe_pruefen) und die heutige
    Task-Liste zurückgeben, wie GET /tasks. Läuft zusätzlich als
    Hintergrund-Schleife im Backend (app/tick.py), der Endpoint hält die UI aktuell."""
    rollover_ausfuehren(db)
    uebergabe_pruefen(db)
    return list(
        db.scalars(
            select(Task)
            .where(Task.erledigt_am.is_(None), Task.geplant_am == date.today())
            .order_by(Task.position)
        )
    )


@router.post("/queue/feierabend", response_model=list[TaskOut])
def feierabend(db: Session = Depends(get_db)) -> list[Task]:
    """Feierabend: alle aktiven Tasks wandern auf next, ihre aktiv-Phasen enden.
    Der automatische Statuswechsel bleibt danach still, bis wieder etwas aktiv ist."""
    tasks = list(
        db.scalars(
            select(Task)
            .where(Task.erledigt_am.is_(None), Task.geplant_am == date.today())
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
    """Nimmt die komplette Ziel-Reihenfolge eines Tages entgegen (wie nach dem
    Drag & Drop), Default heute."""
    ziel = daten.datum or date.today()
    tasks = {
        t.id: t
        for t in db.scalars(
            select(Task).where(Task.erledigt_am.is_(None), Task.geplant_am == ziel)
        )
    }
    if set(daten.task_ids) != set(tasks) or len(daten.task_ids) != len(tasks):
        raise HTTPException(
            422, "task_ids muss jede offene Task-Id des Tages genau einmal enthalten"
        )
    for position, task_id in enumerate(daten.task_ids, start=1):
        tasks[task_id].position = position
    db.commit()
    return sorted(tasks.values(), key=lambda t: t.position)
