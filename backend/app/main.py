from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import schedule, tasks, timeblocks


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Für Dev und Tests. Produktiv-Migrationen laufen über Alembic.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="smierx-queue", version="0.1.0", lifespan=lifespan)

# Vite-Dev-Server. Produktion läuft hinter demselben Host, da greift CORS nicht.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(timeblocks.router)
app.include_router(schedule.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
