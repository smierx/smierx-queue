# smierx-queue

Taskmanagement als Queue-System. Tasks tragen Status als Tags (aktiv, inaktiv, pausiert, holding, next, support, discussion, critical), mehrere Tasks können gleichzeitig laufen. Daneben Meetings und andere Blocker mit fixen Zeiträumen plus ein Arbeitszeit-Modell pro Person, daraus rechnet die App die freie Tageskapazität.

Stack: FastAPI + Postgres (backend/), React + Vite (frontend/), Auth über Keycloak (ab Phase 4), optionaler bidirektionaler GitLab-Sync (Phase 5).

## Entwicklung

```sh
# Postgres + Keycloak (+ API im Container)
docker compose up -d db keycloak

# API lokal (Port 8000)
cd backend
uv sync
uv run uvicorn app.main:app --reload

# Frontend (Port 5173, proxied /api → 8000)
cd frontend
npm install
npm run dev
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

Keycloak-Dev-Login: Realm `smierx`, User `michel` / `michel`, Admin-Konsole auf http://localhost:8080 (admin/admin). Wird erst ab Phase 4 von der App genutzt.
