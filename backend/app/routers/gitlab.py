from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import aktueller_user
from app.database import get_db
from app.gitlab_client import GitLabClient
from app.models import GitlabConnection
from app.schemas import ConnectionOut, ConnectionUpdate, SyncResult
from app.sync import sync_ausfuehren

router = APIRouter(tags=["gitlab"])


def client_fuer(verbindung: GitlabConnection) -> GitLabClient:
    """Eigene Funktion, damit Tests hier einen Fake einhängen können."""
    return GitLabClient(verbindung.url, verbindung.token)


def _verbindung_holen(db: Session, user: str) -> GitlabConnection | None:
    return db.scalar(select(GitlabConnection).where(GitlabConnection.user_id == user))


@router.get("/gitlab/connection", response_model=ConnectionOut)
def verbindung_lesen(
    db: Session = Depends(get_db), user: str = Depends(aktueller_user)
) -> GitlabConnection:
    verbindung = _verbindung_holen(db, user)
    if verbindung is None:
        raise HTTPException(404, "Keine GitLab-Verbindung eingerichtet")
    return verbindung


@router.put("/gitlab/connection", response_model=ConnectionOut)
def verbindung_setzen(
    daten: ConnectionUpdate,
    db: Session = Depends(get_db),
    user: str = Depends(aktueller_user),
) -> GitlabConnection:
    verbindung = _verbindung_holen(db, user)
    if verbindung is None:
        verbindung = GitlabConnection(user_id=user)
        db.add(verbindung)
    verbindung.url = daten.url
    if daten.token:  # leer lassen = bestehenden Token behalten
        verbindung.token = daten.token
    verbindung.projekt_ids = daten.projekt_ids
    if not verbindung.token:
        raise HTTPException(422, "token fehlt")
    db.commit()
    db.refresh(verbindung)
    return verbindung


@router.delete("/gitlab/connection", status_code=204)
def verbindung_loeschen(
    db: Session = Depends(get_db), user: str = Depends(aktueller_user)
) -> None:
    verbindung = _verbindung_holen(db, user)
    if verbindung is not None:
        db.delete(verbindung)
        db.commit()


@router.post("/gitlab/sync", response_model=SyncResult)
def sync(db: Session = Depends(get_db), user: str = Depends(aktueller_user)) -> dict:
    verbindung = _verbindung_holen(db, user)
    if verbindung is None:
        raise HTTPException(404, "Keine GitLab-Verbindung eingerichtet")
    return sync_ausfuehren(db, user, client_fuer(verbindung))
