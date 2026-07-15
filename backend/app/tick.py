"""Hintergrund-Tick: automatischer Statuswechsel auch ohne offenen Browser.

Läuft als Asyncio-Task im Lifespan (main.py). Bei mehreren Uvicorn-Workern
liefe die Schleife mehrfach, das Deployment nutzt bewusst einen Worker.
"""

import asyncio
import logging

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Task
from app.routers.tasks import uebergabe_pruefen

logger = logging.getLogger("smierx_queue.tick")


def alle_user_ticken() -> None:
    """Ein Durchlauf: Übergabe für jeden User mit offenen Tasks prüfen."""
    with SessionLocal() as db:
        users = list(
            db.scalars(select(Task.user_id).where(Task.erledigt_am.is_(None)).distinct())
        )
        for user in users:
            uebergabe_pruefen(db, user)


async def tick_schleife() -> None:
    while True:
        await asyncio.sleep(settings.tick_intervall_sekunden)
        try:
            await asyncio.to_thread(alle_user_ticken)
        except Exception:
            logger.exception("Hintergrund-Tick fehlgeschlagen")
