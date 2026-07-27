"""Rollover: offene Tasks vergangener Tage wandern an den Kopf der heutigen Queue.

Läuft lazy (Hintergrund-Tick, /queue/tick, GET /tasks für heute) statt um
Mitternacht, weil der Rechner nachts aus sein kann. Idempotent: nach einem Lauf
liegt kein offener Task mehr in der Vergangenheit.
"""

import logging
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BEREICHE, Task, _phasenzeit

logger = logging.getLogger("smierx_queue.rollover")


def _bereich_rollen(db: Session, bereich: str, heute: date) -> int:
    # Import hier statt oben: routers.tasks importiert dieses Modul.
    from app.routers.tasks import _tag_anwenden

    alte = list(
        db.scalars(
            select(Task)
            .where(
                Task.erledigt_am.is_(None),
                Task.geplant_am < heute,
                Task.bereich == bereich,
            )
            .order_by(Task.geplant_am, Task.position)
        )
    )
    if not alte:
        return 0

    heutige = list(
        db.scalars(
            select(Task)
            .where(
                Task.erledigt_am.is_(None),
                Task.geplant_am == heute,
                Task.bereich == bereich,
            )
            .order_by(Task.position)
        )
    )
    mitternacht = datetime.combine(heute, time.min)
    for task in alte:
        # Vergessener Feierabend: die offene Phase endet um Mitternacht,
        # aktiv wird zu next. Falsch verbuchte Zeit ist retro korrigierbar.
        # Startete die Phase erst nach Mitternacht (Task nachträglich
        # zurückdatiert), endet sie an ihrem eigenen Start statt davor.
        if "aktiv" in task.tags:
            for phase in task.phasen:
                if phase.bis is None:
                    phase.bis = max(mitternacht, _phasenzeit(phase.von))
            _tag_anwenden(task, "next")
        task.geplant_am = heute
    # Carry-Tasks an den Kopf, der heutige Bestand rückt dahinter.
    for position, task in enumerate(alte + heutige, start=1):
        task.position = position
    return len(alte)


def rollover_ausfuehren(db: Session) -> int:
    """Rollt beide Bereiche unabhängig. Gibt die Gesamtzahl der verschobenen
    Tasks zurück, committet selbst."""
    heute = date.today()
    verschoben = sum(_bereich_rollen(db, bereich, heute) for bereich in sorted(BEREICHE))
    if verschoben:
        db.commit()
        logger.info("Rollover: %s Task(s) auf heute geschoben", verschoben)
    return verschoben
