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


def tick_durchlauf() -> None:
    """Ein Durchlauf: Übergabe prüfen, wenn offene Tasks existieren."""
    with SessionLocal() as db:
        hat_offene = db.scalar(select(Task.id).where(Task.erledigt_am.is_(None)).limit(1))
        if hat_offene is not None:
            uebergabe_pruefen(db)


async def tick_schleife() -> None:
    while True:
        await asyncio.sleep(settings.tick_intervall_sekunden)
        try:
            await asyncio.to_thread(tick_durchlauf)
        except Exception:
            logger.exception("Hintergrund-Tick fehlgeschlagen")
