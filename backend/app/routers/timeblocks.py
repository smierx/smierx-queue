from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TimeBlock
from app.schemas import TimeBlockCreate, TimeBlockOut

router = APIRouter(tags=["timeblocks"])


def _block_holen(db: Session, block_id: int) -> TimeBlock:
    block = db.get(TimeBlock, block_id)
    if block is None:
        raise HTTPException(404, f"Termin/Blocker {block_id} nicht gefunden")
    return block


@router.get("/timeblocks", response_model=list[TimeBlockOut])
def timeblocks_auflisten(
    von: date | None = None,
    bis: date | None = None,
    db: Session = Depends(get_db),
) -> list[TimeBlock]:
    """Alle Blöcke, optional auf einen Datumsbereich eingegrenzt (Überlappung zählt)."""
    stmt = select(TimeBlock).order_by(TimeBlock.start)
    if von is not None:
        stmt = stmt.where(TimeBlock.ende > datetime.combine(von, time.min))
    if bis is not None:
        stmt = stmt.where(TimeBlock.start < datetime.combine(bis, time.max))
    return list(db.scalars(stmt))


@router.post("/timeblocks", response_model=TimeBlockOut, status_code=201)
def timeblock_anlegen(
    daten: TimeBlockCreate,
    db: Session = Depends(get_db),
) -> TimeBlock:
    block = TimeBlock(**daten.model_dump())
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


@router.put("/timeblocks/{block_id}", response_model=TimeBlockOut)
def timeblock_aendern(
    block_id: int,
    daten: TimeBlockCreate,
    db: Session = Depends(get_db),
) -> TimeBlock:
    block = _block_holen(db, block_id)
    for feld, wert in daten.model_dump().items():
        setattr(block, feld, wert)
    db.commit()
    db.refresh(block)
    return block


@router.delete("/timeblocks/{block_id}", status_code=204)
def timeblock_loeschen(
    block_id: int,
    db: Session = Depends(get_db),
) -> None:
    db.delete(_block_holen(db, block_id))
    db.commit()
