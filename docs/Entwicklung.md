# smierx-queue entwickeln

Architektur, Konventionen und Abläufe. Was Nutzer sehen steht in [Nutzung.md](Nutzung.md), Setup-Befehle in der [README](../README.md).

## Überblick

Solo-App: genau ein Anwender, eine Instanz, kein Login. Monorepo mit zwei Teilen und einem gemeinsamen Image:

```
backend/     FastAPI + SQLAlchemy + Alembic, Python via uv
frontend/    React + TypeScript + Vite
Dockerfile   Multi-Stage: baut das Frontend, die API liefert es als Static aus
```

Im Betrieb gibt es genau einen App-Container: die API served das gebaute Frontend unter `/`, alle API-Routen liegen unter `/api`, Migrationen laufen beim Start. Der Port bindet nur auf 127.0.0.1, das ist der ganze Zugriffsschutz.

## Backend

### Module

| Modul | Aufgabe |
|---|---|
| `app/main.py` | App-Setup, Lifespan (Tick-Schleife, `create_all` für Dev/Tests), Static-Mount |
| `app/config.py` | Settings über pydantic-settings, alles per Env-Var überschreibbar |
| `app/models.py` | SQLAlchemy-Modelle plus Tag-Katalog (`VALID_TAGS`, `ZUSTAND_TAGS`, `TIMEBLOCK_TYPEN`) |
| `app/schemas.py` | Pydantic-Schemas für Ein- und Ausgabe |
| `app/routers/` | `tasks` (CRUD, Tags, Queue, Tick, Feierabend), `timeblocks`, `schedule` (+ Kapazität), `export` |
| `app/tick.py` | Hintergrund-Schleife: ruft die Übergabe-Prüfung, wenn offene Tasks existieren |

### Datenmodell

- **Task**: Titel, Beschreibung, `position` (Queue-Reihenfolge), `dauer_minuten`, `erledigt_am` (gesetzt = Archiv statt Löschen).
- **TaskTag** + **TagEvent**: Tags als Zeilen plus Historie (`gesetzt`/`entfernt`). Zustand-Tags verdrängen sich gegenseitig in `_tag_anwenden()`. Aus der Historie werden `aktiv_phasen` und `aktiv_seit` berechnet, davon lebt der Zeitstrahl.
- **TimeBlock**: Meetings/Blocker/Support mit Start und Ende.
- **WorkSchedule**: das Arbeitszeit-Modell, genau eine Zeile (feste Id 1), Modus `stunden` oder `feste_zeiten`. Get-or-Create ist race-sicher (parallele erste Requests kollidieren am Primärschlüssel).

### Queue-Mechanik

Kern ist `uebergabe_pruefen()` in `routers/tasks.py`: sind Tasks aktiv, aber keiner mehr in seiner geplanten Zeit (aktiv seit + Dauer, Blocker-Fenster schieben das Ende nach hinten), wird der nächste wartende Task aktiv. `next` zuerst, geparkte (`pausiert`, `holding`, `inaktiv`) übersprungen, höchstens ein Wechsel, ohne aktive Tasks passiert nichts, mitten im Blocker auch nicht. Der Endpoint `POST /queue/tick` und die Hintergrund-Schleife (`app/tick.py`, `TICK_INTERVALL_SEKUNDEN`) rufen dieselbe Funktion.

**Wichtig:** die Schleife läuft im Lifespan. Bei mehreren Uvicorn-Workern liefe sie mehrfach, das Deployment nutzt deshalb bewusst **einen Worker**.

### Zeitzonen-Konvention

Die App rechnet fachlich in **lokaler, naiver Zeit** (TimeBlocks, `aktiv_phasen`, „heute", Tagesfenster, Export-Wochen). DB-Timestamps mit Server-Default sind UTC und werden über `_lokal()` konvertiert. Deshalb braucht der Container `TZ` (Default im Compose `Europe/Berlin`), sonst kippt „heute" um 22 Uhr.

### API

Alle Routen unter `/api`, dazu `GET /health`. Kurzüberblick:

| Bereich | Endpunkte |
|---|---|
| Tasks | `GET/POST /tasks`, `GET/PATCH/DELETE /tasks/{id}`, `PUT/DELETE /tasks/{id}/tags/{tag}`, `POST/DELETE /tasks/{id}/erledigt`, `GET /tasks/{id}/historie` |
| Queue | `PUT /queue/order` (komplette Ziel-Reihenfolge), `POST /queue/tick`, `POST /queue/feierabend` |
| Zeitblöcke | `GET/POST /timeblocks`, `PUT/DELETE /timeblocks/{id}` |
| Arbeitszeit | `GET/PUT /schedule`, `GET /capacity` |
| Export | `GET /export?woche=JJJJ-WXX` |

Interaktive Doku wie bei FastAPI üblich unter `/docs`.

## Frontend

SPA ohne Router, `App.tsx` hält den Zustand und lädt alles über `api.ts`. Komponenten:

- `Tagesleiste.tsx`: der Zeitstrahl. Achsen-Layout, Task-Ebenen, Blocker-Splitting, Dauer-Ziehen, Scrollen. Die mit Abstand komplexeste Komponente.
- `TaskDetail.tsx`: Task-Modal mit Tag-Historie.
- `SchedulePanel.tsx`: Arbeitszeit-Modell.

Im Dev proxied Vite `/api` auf das Backend (`VITE_API_TARGET`, Default localhost:8000).

## Tests und Qualität

```sh
cd backend
uv run pytest          # SQLite in-memory, kein Docker nötig
uv run ruff check .
cd ../frontend
npm run build          # tsc + vite, dient auch als Typcheck
```

Die Tests decken die Fachlogik ab (Tags, Übergabe, Blocker-Rechnung, Kapazität, Export). Neue Fachlogik bekommt einen Test, Testnamen sind deutsch und beschreiben das Verhalten (`test_tick_wartet_im_blocker`).

## Migrationen

```sh
cd backend
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "beschreibung"
```

Beim Container-Start laufen Migrationen automatisch. `create_all` im Lifespan ist nur für Dev und Tests. Neue Migration immer gegen eine frische DB durchlaufen lassen.

## Betrieb

CI (`.github/workflows/ci.yml`) fährt pytest, ruff und den Frontend-Build. Deployt wird nicht: die App läuft lokal über das Root-Compose (`docker compose up -d --build`). Die wichtigsten Env-Vars:

| Variable | Bedeutung |
|---|---|
| `DATABASE_URL` | SQLAlchemy-URL (`postgresql+psycopg://…`) |
| `TZ` | Zeitzone der App, Default im Compose `Europe/Berlin` |
| `TICK_INTERVALL_SEKUNDEN` | Hintergrund-Tick, Default 60, `0` schaltet ihn ab |

## Konventionen

- Code-Kommentare, Docstrings, Testnamen und Commit-Messages auf Deutsch, Commits im Conventional-Commits-Stil (`feat:`, `fix:`, `chore:`, `docs:`).
- Fachbegriffe bleiben deutsch (Übergabe, Feierabend, Tagesleiste), API-Feldnamen auch (`dauer_minuten`, `erledigt_am`).
- Ein Datum/Zeit-Prinzip: fachlich lokale naive Zeit, siehe Zeitzonen-Konvention oben.
- Secrets nie ins Repo: `.env*` ist gitignored.
