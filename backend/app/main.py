import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine
from app.routers import export, phasen, schedule, tasks, timeblocks
from app.tick import tick_schleife

# Uvicorn konfiguriert nur seine eigenen Logger. Ohne das hier landen die
# smierx_queue.*-Logs (Tick, Sync) nirgends.
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Für Dev und Tests. Produktiv-Migrationen laufen über Alembic.
    Base.metadata.create_all(engine)
    # Hintergrund-Tick: Statuswechsel laufen auch ohne offenen Browser.
    schleife = (
        asyncio.create_task(tick_schleife()) if settings.tick_intervall_sekunden > 0 else None
    )
    yield
    if schleife is not None:
        schleife.cancel()


app = FastAPI(title="smierx-queue", version="0.1.0", lifespan=lifespan)

# Vite-Dev-Server. Produktion läuft hinter demselben Host, da greift CORS nicht.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router, prefix="/api")
app.include_router(phasen.router, prefix="/api")
app.include_router(timeblocks.router, prefix="/api")
app.include_router(schedule.router, prefix="/api")
app.include_router(export.router, prefix="/api")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Im Produktions-Image liegt das gebaute Frontend unter static/.
_static = Path(__file__).parent.parent / "static"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="frontend")
