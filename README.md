# smierx-queue

Taskmanagement als Queue-System, als Solo-App für genau eine Person auf einem Rechner. Tasks tragen Status als Tags (aktiv, inaktiv, pausiert, holding, next, discussion, critical), mehrere Tasks können gleichzeitig laufen. Daneben Meetings und andere Blocker mit fixen Zeiträumen plus ein Arbeitszeit-Modell, daraus rechnet die App die freie Tageskapazität.

Stack: FastAPI + Postgres (backend/), React + Vite (frontend/). Kein Login, kein Multi-User: die App bindet nur auf 127.0.0.1, die Erreichbarkeit ist der Schutz.

Doku: [Nutzung](docs/Nutzung.md) (Bedienung, Queue-Mechanik, Export) und [Entwicklung](docs/Entwicklung.md) (Architektur, Konventionen).

## Betrieb

Der komplette Stack (Postgres + App als ein Image, Frontend wird im Build eingebacken):

```sh
docker compose up -d --build
# UI: http://127.0.0.1:8010
```

## Entwicklung

Nur die DB im Container, API und Frontend nativ mit Hot Reload:

```sh
docker compose up -d db

cd backend
uv sync
uv run uvicorn app.main:app --reload   # Port 8000

cd frontend
npm install
npm run dev                            # Port 5173, proxied /api → 8000
```

Tests und Lint:

```sh
cd backend
uv run pytest
uv run ruff check .
```

Migrationen:

```sh
cd backend
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "…"
```

CI (`.github/workflows/ci.yml`) fährt Backend-Tests, Lint und den Frontend-Build.
