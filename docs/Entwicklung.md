# smierx-queue entwickeln

Architektur, Konventionen und Abläufe. Was Nutzer sehen steht in [Nutzung.md](Nutzung.md), Setup-Befehle in der [README](../README.md).

## Überblick

Monorepo mit zwei Teilen und einem gemeinsamen Produktions-Image:

```
backend/     FastAPI + SQLAlchemy + Alembic, Python via uv
frontend/    React + TypeScript + Vite
Dockerfile   Multi-Stage: baut das Frontend, die API liefert es als Static aus
keycloak/    Realm-Import fürs lokale Dev-Compose (User michel/michel)
```

Produktiv gibt es genau einen Container: die API served das gebaute Frontend unter `/`, alle API-Routen liegen unter `/api`, Migrationen laufen beim Start. Das Frontend holt seine Konfiguration zur Laufzeit von `GET /api/config`, ins Image wird nichts eingebacken.

## Backend

### Module

| Modul | Aufgabe |
|---|---|
| `app/main.py` | App-Setup, Lifespan (Tick-Schleife, `create_all` für Dev/Tests), Static-Mount, `/api/config` |
| `app/config.py` | Settings über pydantic-settings, alles per Env-Var überschreibbar |
| `app/auth.py` | `aktueller_user()`-Dependency: OIDC-Token-Validierung oder Dev-Modus |
| `app/models.py` | SQLAlchemy-Modelle plus Tag-Katalog (`VALID_TAGS`, `ZUSTAND_TAGS`, `TIMEBLOCK_TYPEN`) |
| `app/schemas.py` | Pydantic-Schemas für Ein- und Ausgabe |
| `app/routers/` | `tasks` (CRUD, Tags, Queue, Tick, Feierabend), `timeblocks`, `schedule` (+ Kapazität), `gitlab`, `export` |
| `app/tick.py` | Hintergrund-Schleife: ruft die Übergabe-Prüfung für alle User mit offenen Tasks |
| `app/sync.py` | GitLab-Sync-Logik (Import, Rückrichtung, Konflikte, Log) |
| `app/gitlab_client.py` | Dünner HTTP-Client für die GitLab-API, paginiert über alle Seiten |

### Datenmodell

Alles hängt an `user_id` (Keycloak `preferred_username`, im Dev-Modus `dev`), jede Query filtert darauf.

- **Task**: Titel, Beschreibung, `position` (Queue-Reihenfolge pro User), `dauer_minuten`, `erledigt_am` (gesetzt = Archiv statt Löschen).
- **TaskTag** + **TagEvent**: Tags als Zeilen plus Historie (`gesetzt`/`entfernt`). Zustand-Tags verdrängen sich gegenseitig in `_tag_anwenden()`. Aus der Historie werden `aktiv_phasen` und `aktiv_seit` berechnet, davon lebt der Zeitstrahl.
- **TimeBlock**: Meetings/Blocker/Support mit Start und Ende.
- **WorkSchedule**: Arbeitszeit pro User, Modus `stunden` oder `feste_zeiten`. Get-or-Create ist race-sicher (parallele erste Requests).
- **GitlabConnection**, **GitlabLink**, **SyncLog**: eine Verbindung pro User, Task↔Issue-Links mit Dedup, persistentes Aktivitätslog.

### Queue-Mechanik

Kern ist `uebergabe_pruefen()` in `routers/tasks.py`: sind Tasks aktiv, aber keiner mehr in seiner geplanten Zeit (aktiv seit + Dauer, Blocker-Fenster schieben das Ende nach hinten), wird der nächste wartende Task aktiv. `next` zuerst, geparkte (`pausiert`, `holding`, `inaktiv`) übersprungen, höchstens ein Wechsel, ohne aktive Tasks passiert nichts, mitten im Blocker auch nicht. Der Endpoint `POST /queue/tick` und die Hintergrund-Schleife (`app/tick.py`, `TICK_INTERVALL_SEKUNDEN`) rufen dieselbe Funktion.

**Wichtig:** die Schleife läuft im Lifespan. Bei mehreren Uvicorn-Workern liefe sie mehrfach, das Deployment nutzt deshalb bewusst **einen Worker**.

### Zeitzonen-Konvention

Die App rechnet fachlich in **lokaler, naiver Zeit** (TimeBlocks, `aktiv_phasen`, „heute", Tagesfenster, Export-Wochen). DB-Timestamps mit Server-Default sind UTC und werden über `_lokal()` konvertiert. Der GitLab-Sync vergleicht konsequent UTC-naiv. Deshalb braucht der Container `TZ` (Default in den Compose-Dateien `Europe/Berlin`), sonst kippt „heute" um 22 Uhr.

### Auth

Ohne `OIDC_ISSUER` gibt `aktueller_user()` fest `dev` zurück, kein Token nötig. Mit Issuer: RS256-Validierung gegen die JWKS (Issuer-Check, kein Audience-Check, Keycloak setzt da nur `account`). Die User-Id ist `preferred_username`, nicht `sub`: Daten überleben so einen Realm-Neubau. Kehrseite: wird ein Username neu vergeben, erbt die Person die Daten. `OIDC_JWKS_URL` nur setzen, wenn der Container den Issuer-Host nicht auflösen kann.

### API

Alle Routen unter `/api`, dazu `GET /health`. Kurzüberblick:

| Bereich | Endpunkte |
|---|---|
| Tasks | `GET/POST /tasks`, `GET/PATCH/DELETE /tasks/{id}`, `PUT/DELETE /tasks/{id}/tags/{tag}`, `POST/DELETE /tasks/{id}/erledigt`, `GET /tasks/{id}/historie` |
| Queue | `PUT /queue/order` (komplette Ziel-Reihenfolge), `POST /queue/tick`, `POST /queue/feierabend` |
| Zeitblöcke | `GET/POST /timeblocks`, `PUT/DELETE /timeblocks/{id}` |
| Arbeitszeit | `GET/PUT /schedule`, `GET /capacity` |
| GitLab | `GET/PUT/DELETE /gitlab/connection`, `POST /gitlab/sync`, `GET /gitlab/log` |
| Export | `GET /export?woche=JJJJ-WXX` |
| Config | `GET /api/config` (Frontend-Laufzeit-Config) |

Interaktive Doku wie bei FastAPI üblich unter `/docs`.

## Frontend

SPA ohne Router, `App.tsx` hält den Zustand und lädt alles über `api.ts` (setzt das Bearer-Token, wenn Keycloak aktiv ist). `main.tsx` holt `/api/config`: mit `keycloak_url` läuft keycloak-js (`login-required`, PKCE), ohne startet die App direkt. Komponenten:

- `Tagesleiste.tsx`: der Zeitstrahl. Achsen-Layout, Task-Ebenen, Blocker-Splitting, Dauer-Ziehen, Scrollen. Die mit Abstand komplexeste Komponente.
- `TaskDetail.tsx`: Task-Modal mit Tag-Historie.
- `SchedulePanel.tsx`: Arbeitszeit-Modell.
- `GitLabPanel.tsx`: Verbindung, Sync-Knopf, Log.

Im Dev proxied Vite `/api` auf das Backend (`VITE_API_TARGET`, Default localhost:8000).

## Tests und Qualität

```sh
cd backend
uv run pytest          # SQLite in-memory, kein Docker nötig
uv run ruff check .
cd ../frontend
npm run build          # tsc + vite, dient auch als Typcheck
```

Die Tests decken die Fachlogik ab (Tags, Übergabe, Blocker-Rechnung, Kapazität, Export, GitLab-Sync mit gemocktem Client, Auth mit selbst signierten Tokens). Neue Fachlogik bekommt einen Test, Testnamen sind deutsch und beschreiben das Verhalten (`test_tick_wartet_im_blocker`).

## Migrationen

```sh
cd backend
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "beschreibung"
```

Produktiv laufen Migrationen automatisch beim Container-Start. `create_all` im Lifespan ist nur für Dev und Tests. Neue Migration immer gegen eine frische DB durchlaufen lassen.

## Deployment

CI (`.github/workflows/build.yml`) testet (pytest, ruff, Frontend-Build) und pusht das Image nach GHCR (`ghcr.io/smierx/smierx-queue:latest`, linux/amd64). `main` bleibt immer deploybar. Drei Compose-Varianten fürs Ausrollen:

| Datei | Szenario | DB | Auth |
|---|---|---|---|
| `docker-compose.prod.yml` | Standard-Deploy | eigener Postgres-Container | Keycloak extern |
| `docker-compose.home.yml` | zentrale Postgres im Netz `db-internal` | extern | Keycloak extern |
| `docker-compose.noauth.yml` | Single-User ohne Identity Provider | eigener Postgres-Container | keiner (Dev-Modus, Port default nur 127.0.0.1) |

Alle drei mit Watchtower (label-gated) für automatische Image-Updates. Die wichtigsten Env-Vars:

| Variable | Bedeutung |
|---|---|
| `DATABASE_URL` | SQLAlchemy-URL (`postgresql+psycopg://…`) |
| `TZ` | Zeitzone der App, Default in den Compose-Dateien `Europe/Berlin` |
| `TICK_INTERVALL_SEKUNDEN` | Hintergrund-Tick, Default 60, `0` schaltet ihn ab |
| `OIDC_ISSUER` | Keycloak-Realm-URL; leer = Dev-Modus ohne Login |
| `OIDC_JWKS_URL` | nur wenn der Container den Issuer nicht auflösen kann |
| `FRONTEND_KEYCLOAK_URL` / `_REALM` / `_CLIENT` | was `/api/config` ans Frontend gibt; URL leer = Frontend ohne Login |

## Konventionen

- Code-Kommentare, Docstrings, Testnamen und Commit-Messages auf Deutsch, Commits im Conventional-Commits-Stil (`feat:`, `fix:`, `chore:`, `docs:`).
- Fachbegriffe bleiben deutsch (Übergabe, Feierabend, Tagesleiste), API-Feldnamen auch (`dauer_minuten`, `erledigt_am`).
- Ein Datum/Zeit-Prinzip: fachlich lokale naive Zeit, siehe Zeitzonen-Konvention oben.
- Secrets nie ins Repo: `.env*` ist gitignored, nur die `*.example`-Dateien sind versioniert.
