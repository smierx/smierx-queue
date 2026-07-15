import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import aktueller_user
from app.database import get_db
from app.models import (
    VALID_TAGS,
    ZUSTAND_TAGS,
    GitlabConnection,
    GitlabLink,
    SyncLog,
    TagEvent,
    Task,
    TaskTag,
    TimeBlock,
)
from app.schemas import QueueOrder, TagEventOut, TaskCreate, TaskOut, TaskUpdate

router = APIRouter(tags=["tasks"])
logger = logging.getLogger("smierx_queue.tasks")


def _jetzt_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _issue_status_setzen(db: Session, task: Task, state_event: str) -> None:
    """Verlinktes GitLab-Issue schließen/öffnen. Fehler blockieren das Erledigen nicht."""
    link = db.scalar(select(GitlabLink).where(GitlabLink.task_id == task.id))
    if link is None:
        return
    verbindung = db.scalar(
        select(GitlabConnection).where(GitlabConnection.user_id == task.user_id)
    )
    if verbindung is None:
        return
    from app.routers.gitlab import client_fuer

    details = {"projekt_id": link.projekt_id, "issue_iid": link.issue_iid, "task_id": task.id}
    try:
        client_fuer(verbindung).issue_aktualisieren(
            link.projekt_id, link.issue_iid, state_event=state_event
        )
        details["ok"] = True
        logger.info(
            "Issue %s#%s: %s (Task %s)", link.projekt_id, link.issue_iid, state_event, task.id
        )
    except Exception as fehler:
        details["ok"] = False
        details["fehler"] = str(fehler)
        logger.warning(
            "Issue %s#%s konnte nicht per %s aktualisiert werden: %s",
            link.projekt_id, link.issue_iid, state_event, fehler,
        )
    aktion = "issue_close" if state_event == "close" else "issue_reopen"
    db.add(SyncLog(user_id=task.user_id, aktion=aktion, details=details))


def _task_holen(db: Session, task_id: int, user: str) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.user_id != user:
        raise HTTPException(404, f"Task {task_id} nicht gefunden")
    return task


def _tag_pruefen(tag: str) -> str:
    if tag not in VALID_TAGS:
        raise HTTPException(422, f"Unbekanntes Tag {tag!r}. Gültig sind: {sorted(VALID_TAGS)}")
    return tag


def _tag_anwenden(task: Task, tag: str) -> None:
    """Tag setzen inkl. Historie. Zustand-Tags verdrängen sich gegenseitig."""
    if tag in ZUSTAND_TAGS:
        for zeile in [z for z in task.tag_zeilen if z.tag in ZUSTAND_TAGS and z.tag != tag]:
            task.tag_zeilen.remove(zeile)
            task.historie.append(TagEvent(tag=zeile.tag, aktion="entfernt"))
    if tag not in task.tags:
        task.tag_zeilen.append(TaskTag(tag=tag))
        task.historie.append(TagEvent(tag=tag, aktion="gesetzt"))


@router.get("/tasks", response_model=list[TaskOut])
def tasks_auflisten(
    tag: str | None = None,
    erledigt: bool = False,
    db: Session = Depends(get_db),
    user: str = Depends(aktueller_user),
) -> list[Task]:
    stmt = select(Task).where(Task.user_id == user)
    if erledigt:
        stmt = stmt.where(Task.erledigt_am.is_not(None)).order_by(Task.erledigt_am.desc())
    else:
        stmt = stmt.where(Task.erledigt_am.is_(None)).order_by(Task.position)
    if tag is not None:
        _tag_pruefen(tag)
        stmt = stmt.join(TaskTag).where(TaskTag.tag == tag)
    return list(db.scalars(stmt))


@router.post("/tasks", response_model=TaskOut, status_code=201)
def task_anlegen(
    daten: TaskCreate,
    db: Session = Depends(get_db),
    user: str = Depends(aktueller_user),
) -> Task:
    max_position = db.scalar(select(func.max(Task.position)).where(Task.user_id == user))
    task = Task(
        user_id=user,
        titel=daten.titel,
        beschreibung=daten.beschreibung,
        position=(max_position or 0) + 1,
        dauer_minuten=daten.dauer_minuten,
    )
    task.tag_zeilen = [TaskTag(tag=t) for t in daten.tags]
    task.historie = [TagEvent(tag=t, aktion="gesetzt") for t in daten.tags]
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("/tasks/{task_id}", response_model=TaskOut)
def task_lesen(
    task_id: int, db: Session = Depends(get_db), user: str = Depends(aktueller_user)
) -> Task:
    return _task_holen(db, task_id, user)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def task_aendern(
    task_id: int,
    daten: TaskUpdate,
    db: Session = Depends(get_db),
    user: str = Depends(aktueller_user),
) -> Task:
    task = _task_holen(db, task_id, user)
    if daten.titel is not None:
        task.titel = daten.titel
    if daten.beschreibung is not None:
        task.beschreibung = daten.beschreibung
    if daten.dauer_minuten is not None:
        task.dauer_minuten = daten.dauer_minuten
    db.commit()
    db.refresh(task)
    return task


@router.delete("/tasks/{task_id}", status_code=204)
def task_loeschen(
    task_id: int, db: Session = Depends(get_db), user: str = Depends(aktueller_user)
) -> None:
    db.delete(_task_holen(db, task_id, user))
    db.commit()


@router.put("/tasks/{task_id}/tags/{tag}", response_model=TaskOut)
def tag_setzen(
    task_id: int,
    tag: str,
    db: Session = Depends(get_db),
    user: str = Depends(aktueller_user),
) -> Task:
    task = _task_holen(db, task_id, user)
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
    user: str = Depends(aktueller_user),
) -> Task:
    task = _task_holen(db, task_id, user)
    _tag_pruefen(tag)
    zeile = next((z for z in task.tag_zeilen if z.tag == tag), None)
    if zeile is not None:
        task.tag_zeilen.remove(zeile)
        task.historie.append(TagEvent(tag=tag, aktion="entfernt"))
        db.commit()
        db.refresh(task)
    return task


@router.post("/tasks/{task_id}/erledigt", response_model=TaskOut)
def task_erledigen(
    task_id: int, db: Session = Depends(get_db), user: str = Depends(aktueller_user)
) -> Task:
    """Task ins Archiv statt löschen. Ein verlinktes GitLab-Issue wird geschlossen."""
    task = _task_holen(db, task_id, user)
    if task.erledigt_am is None:
        task.erledigt_am = _jetzt_utc()
        _issue_status_setzen(db, task, "close")
        db.commit()
        db.refresh(task)
    return task


@router.delete("/tasks/{task_id}/erledigt", response_model=TaskOut)
def task_wieder_oeffnen(
    task_id: int, db: Session = Depends(get_db), user: str = Depends(aktueller_user)
) -> Task:
    task = _task_holen(db, task_id, user)
    if task.erledigt_am is not None:
        task.erledigt_am = None
        max_position = db.scalar(select(func.max(Task.position)).where(Task.user_id == user))
        task.position = (max_position or 0) + 1  # hinten wieder einreihen
        _issue_status_setzen(db, task, "reopen")
        db.commit()
        db.refresh(task)
    return task


@router.get("/tasks/{task_id}/historie", response_model=list[TagEventOut])
def historie_lesen(
    task_id: int, db: Session = Depends(get_db), user: str = Depends(aktueller_user)
) -> list[TagEvent]:
    return _task_holen(db, task_id, user).historie


# Geparkte Tasks überspringt der automatische Statuswechsel.
GEPARKT = {"pausiert", "holding", "inaktiv"}


def _fenster_zusammenfassen(bloecke: list[TimeBlock]) -> list[tuple[datetime, datetime]]:
    """Blocker/Meetings als sortierte, überlappungsfreie Zeitfenster."""
    fenster: list[tuple[datetime, datetime]] = []
    for start, ende in sorted((b.start, b.ende) for b in bloecke):
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


@router.post("/queue/tick", response_model=list[TaskOut])
def queue_tick(
    db: Session = Depends(get_db), user: str = Depends(aktueller_user)
) -> list[Task]:
    """Automatischer Statuswechsel als Übergabe: sind Tasks aktiv, aber keiner mehr
    in seiner geplanten Zeit (aktiv seit + Dauer, Blocker schieben das Ende nach
    hinten), wird der nächste Queue-Task aktiv. Läuft gar nichts (z.B. nach
    Feierabend), bleibt der Tick still. Mitten in einem Blocker passiert nichts.
    Pro Tick höchstens ein Wechsel, geparkte Tasks (pausiert, holding, inaktiv)
    bleiben liegen. Gibt die offene Task-Liste zurück, wie GET /tasks."""
    tasks = list(
        db.scalars(
            select(Task)
            .where(Task.user_id == user, Task.erledigt_am.is_(None))
            .order_by(Task.position)
        )
    )
    jetzt = datetime.now()  # lokale Zeit, konsistent zu aktiv_seit und TimeBlocks
    fenster = _fenster_zusammenfassen(
        list(db.scalars(select(TimeBlock).where(TimeBlock.user_id == user)))
    )
    im_blocker = any(von <= jetzt < bis for von, bis in fenster)
    aktive = [t for t in tasks if "aktiv" in t.tags]
    laeuft_noch = any(
        t.aktiv_seit is not None
        and _geplantes_ende(t.aktiv_seit, t.dauer_minuten, fenster) > jetzt
        for t in aktive
    )
    if aktive and not laeuft_noch and not im_blocker:
        wartende = sorted(
            (t for t in tasks if "aktiv" not in t.tags and not GEPARKT & set(t.tags)),
            key=lambda t: (0 if "next" in t.tags else 1, t.position),
        )
        if wartende:
            naechster = wartende[0]
            _tag_anwenden(naechster, "aktiv")
            db.commit()
            logger.info("Auto-aktiviert: Task %s (%s)", naechster.id, naechster.titel)
    return tasks


@router.post("/queue/feierabend", response_model=list[TaskOut])
def feierabend(
    db: Session = Depends(get_db), user: str = Depends(aktueller_user)
) -> list[Task]:
    """Feierabend: alle aktiven Tasks wandern auf next, ihre aktiv-Phasen enden.
    Der automatische Statuswechsel bleibt danach still, bis wieder etwas aktiv ist."""
    tasks = list(
        db.scalars(
            select(Task)
            .where(Task.user_id == user, Task.erledigt_am.is_(None))
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
    user: str = Depends(aktueller_user),
) -> list[Task]:
    """Nimmt die komplette Ziel-Reihenfolge entgegen (wie nach dem Drag & Drop)."""
    tasks = {
        t.id: t
        for t in db.scalars(
            select(Task).where(Task.user_id == user, Task.erledigt_am.is_(None))
        )
    }
    if set(daten.task_ids) != set(tasks) or len(daten.task_ids) != len(tasks):
        raise HTTPException(422, "task_ids muss jede offene Task-Id genau einmal enthalten")
    for position, task_id in enumerate(daten.task_ids, start=1):
        tasks[task_id].position = position
    db.commit()
    return sorted(tasks.values(), key=lambda t: t.position)
