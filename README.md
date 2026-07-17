# smierx-queue

Taskmanagement als Queue-System. Tasks tragen Status als Tags (aktiv, inaktiv, pausiert, holding, next, support, discussion, critical), mehrere Tasks können gleichzeitig laufen. Daneben Meetings und andere Blocker mit fixen Zeiträumen plus ein Arbeitszeit-Modell pro Person, daraus rechnet die App die freie Tageskapazität.

Stack: FastAPI + Postgres (backend/), React + Vite (frontend/), Auth über Keycloak (optional), optionaler bidirektionaler GitLab-Sync.

Doku: [Nutzung](docs/Nutzung.md) (Bedienung, Queue-Mechanik, Export, Sync) und [Entwicklung](docs/Entwicklung.md) (Architektur, Konventionen, Deployment).

## Entwicklung

Alles in einem Rutsch (Postgres, Keycloak, API, Frontend mit Hot Reload):

```sh
docker compose up -d
# UI: http://localhost:5173 → Login michel/michel (Keycloak-Dev-Realm)
```

Oder API/Frontend nativ für schnellere Iteration (dann ohne Login, User `dev`):

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

## Auth

Ohne `OIDC_ISSUER` läuft die API im Dev-Modus (ein User `dev`, kein Login). Mit Keycloak: `OIDC_ISSUER` (+ optional `OIDC_JWKS_URL` für Container-Netze) fürs Backend, `FRONTEND_KEYCLOAK_URL` steuert den Login-Flow im Frontend. Das Frontend holt seine Config zur Laufzeit von `/api/config`, es wird nichts zur Build-Zeit eingebacken.

Keycloak-Dev-Login: Realm `smierx`, User `michel` / `michel`, Admin-Konsole auf http://localhost:8080 (admin/admin).

## GitLab-Sync (optional)

Pro User über die UI einrichtbar: GitLab-URL, PAT (Scope `api`), Projekt-Ids. `POST /api/gitlab/sync` gleicht ab: offene Issues werden Tasks, geschlossene räumen ihren Task ab, Titel per last-write-wins (GitLab gewinnt bei Konflikt), Tags spiegeln sich als `queue::<tag>`-Labels. Sync ist Polling, kein Webhook: den Endpunkt bei Bedarf per cron anstoßen.

## Deploy (Homeserver)

Ein Image für alles: Multi-Stage-`Dockerfile` im Root baut das Frontend und liefert es über die API aus, Migrationen laufen beim Start. CI (`.github/workflows/build.yml`) testet und pusht nach GHCR, Watchtower zieht Updates:

```sh
cp .env.prod.example .env.prod   # ausfüllen
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

## Deploy ohne Keycloak (Single-User)

Für den Betrieb ohne Identity Provider: die API läuft im Dev-Modus (ein User `dev`), das Frontend startet ohne Login. Eigener Postgres-Container, der App-Port bindet per Default nur auf 127.0.0.1, weil ohne Login allein die Erreichbarkeit schützt:

```sh
cp .env.noauth.example .env.noauth   # ausfüllen
docker compose -f docker-compose.noauth.yml --env-file .env.noauth up -d
```
