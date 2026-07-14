from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import aktueller_user
from app.database import get_db
from app.models import VALID_TAGS, TagEvent, Task, TaskTag
from app.schemas import QueueOrder, TagEventOut, TaskCreate, TaskOut, TaskUpdate

router = APIRouter(tags=["tasks"])


def _task_holen(db: Session, task_id: int, user: str) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.user_id != user:
        raise HTTPException(404, f"Task {task_id} nicht gefunden")
    return task


def _tag_pruefen(tag: str) -> str:
    if tag not in VALID_TAGS:
        raise HTTPException(422, f"Unbekanntes Tag {tag!r}. Gültig sind: {sorted(VALID_TAGS)}")
    return tag


@router.get("/tasks", response_model=list[TaskOut])
def tasks_auflisten(
    tag: str | None = None,
    db: Session = Depends(get_db),
    user: str = Depends(aktueller_user),
) -> list[Task]:
    stmt = select(Task).where(Task.user_id == user).order_by(Task.position)
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
        task.tag_zeilen.append(TaskTag(tag=tag))
        task.historie.append(TagEvent(tag=tag, aktion="gesetzt"))
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


@router.get("/tasks/{task_id}/historie", response_model=list[TagEventOut])
def historie_lesen(
    task_id: int, db: Session = Depends(get_db), user: str = Depends(aktueller_user)
) -> list[TagEvent]:
    return _task_holen(db, task_id, user).historie


@router.put("/queue/order", response_model=list[TaskOut])
def queue_umsortieren(
    daten: QueueOrder,
    db: Session = Depends(get_db),
    user: str = Depends(aktueller_user),
) -> list[Task]:
    """Nimmt die komplette Ziel-Reihenfolge entgegen (wie nach dem Drag & Drop)."""
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.user_id == user))}
    if set(daten.task_ids) != set(tasks) or len(daten.task_ids) != len(tasks):
        raise HTTPException(422, "task_ids muss jede Task-Id genau einmal enthalten")
    for position, task_id in enumerate(daten.task_ids, start=1):
        tasks[task_id].position = position
    db.commit()
    return sorted(tasks.values(), key=lambda t: t.position)
