"""Rollover: offene Tasks vergangener Tage wandern an den Kopf der heutigen Queue.

Läuft lazy (Hintergrund-Tick, /queue/tick, GET /tasks für heute) statt um
Mitternacht, weil der Rechner nachts aus sein kann. Idempotent: nach einem Lauf
liegt kein offener Task mehr in der Vergangenheit.
"""

import logging
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task

logger = logging.getLogger("smierx_queue.rollover")


def rollover_ausfuehren(db: Session) -> int:
    """Gibt die Anzahl der verschobenen Tasks zurück. Committet selbst."""
    # Import hier statt oben: routers.tasks importiert dieses Modul.
    from app.routers.tasks import _offene_phase_schliessen, _tag_anwenden

    heute = date.today()
    alte = list(
        db.scalars(
            select(Task)
            .where(Task.erledigt_am.is_(None), Task.geplant_am < heute)
            .order_by(Task.geplant_am, Task.position)
        )
    )
    if not alte:
        return 0

    heutige = list(
        db.scalars(
            select(Task)
            .where(Task.erledigt_am.is_(None), Task.geplant_am == heute)
            .order_by(Task.position)
        )
    )
    mitternacht = datetime.combine(heute, time.min)
    for task in alte:
        # Vergessener Feierabend: die offene Phase endet um Mitternacht,
        # aktiv wird zu next. Falsch verbuchte Zeit ist retro korrigierbar.
        if "aktiv" in task.tags:
            _offene_phase_schliessen(task, mitternacht)
            _tag_anwenden(task, "next")
        task.geplant_am = heute
    # Carry-Tasks an den Kopf, der heutige Bestand rückt dahinter.
    for position, task in enumerate(alte + heutige, start=1):
        task.position = position
    db.commit()
    logger.info("Rollover: %s Task(s) auf heute geschoben", len(alte))
    return len(alte)
