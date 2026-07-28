"""Hintergrund-Tick: hält den Tages-Rollover am Laufen, auch ohne offenen
Browser (z.B. über Mitternacht). Automatische Statuswechsel gibt es seit dem
Entscheid vom 2026-07-28 nicht mehr, die Dauer ist nur eine Schätzung.

Läuft als Asyncio-Task im Lifespan (main.py). Bei mehreren Uvicorn-Workern
liefe die Schleife mehrfach, das Deployment nutzt bewusst einen Worker.
"""

import asyncio
import logging

from app.config import settings
from app.database import SessionLocal
from app.rollover import rollover_ausfuehren

logger = logging.getLogger("smierx_queue.tick")


def tick_durchlauf() -> None:
    """Ein Durchlauf: nur der Rollover."""
    with SessionLocal() as db:
        rollover_ausfuehren(db)


async def tick_schleife() -> None:
    while True:
        await asyncio.sleep(settings.tick_intervall_sekunden)
        try:
            await asyncio.to_thread(tick_durchlauf)
        except Exception:
            logger.exception("Hintergrund-Tick fehlgeschlagen")
