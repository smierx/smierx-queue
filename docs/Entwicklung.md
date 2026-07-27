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
| `app/routers/` | `tasks` (CRUD, Tags, Queue, Tick, Feierabend), `phasen` (Tages-Timeline + Nachtragen), `timeblocks`, `schedule` (+ Kapazität), `export` |
| `app/rollover.py` | Offene Tasks vergangener Tage auf heute schieben (lazy, idempotent) |
| `app/tick.py` | Hintergrund-Schleife: Rollover + Übergabe-Prüfung, wenn offene Tasks existieren |

### Datenmodell

- **Task**: Titel, Beschreibung, `geplant_am` (der Tag, auf dem der Task liegt), `position` (Queue-Reihenfolge pro Tag), `dauer_minuten`, `erledigt_am` (gesetzt = Archiv statt Löschen). Invariante: jeder offene Task liegt auf genau einem Tag ≥ heute.
- **TaskPhase**: explizite aktiv-Phasen (`von`, `bis`, `bis=NULL` = läuft). Die Tag-Logik schreibt sie direkt (aktiv setzen öffnet, verlieren schließt), fürs Nachtragen sind sie per CRUD editierbar. Invariante: aktiv-Tag ⟺ genau eine offene Phase. Davon leben Zeitstrahl und Export.
- **TaskTag** + **TagEvent**: Tags als Zeilen plus reine Anzeige-Historie (`gesetzt`/`entfernt`). Zustand-Tags verdrängen sich gegenseitig in `_tag_anwenden()`.
- **TimeBlock**: Meetings/Blocker/Support mit Start und Ende.
- **WorkSchedule**: das Arbeitszeit-Modell, genau eine Zeile (feste Id 1), Modus `stunden` oder `feste_zeiten`. Get-or-Create ist race-sicher (parallele erste Requests kollidieren am Primärschlüssel).

### Rollover

`app/rollover.py`: offene Tasks mit `geplant_am < heute` wandern an den Kopf der heutigen Queue (Reihenfolge nach Tag und Position erhalten, geparkte wandern mit). Läuft er auf eine vergessene offene Phase, schließt er sie um Mitternacht (bzw. am Phasen-Start, falls der später liegt) und dreht `aktiv` auf `next`. Der Rollover läuft **lazy** statt um Mitternacht (der Rechner kann nachts aus sein): am Anfang des Hintergrund-Ticks, von `POST /queue/tick` und von `GET /tasks` für heute. Idempotent, eine Transaktion.

### Queue-Mechanik

Kern ist `uebergabe_pruefen()` in `routers/tasks.py`: sind Tasks aktiv, aber keiner mehr in seiner geplanten Zeit (aktiv seit + Dauer, Blocker-Fenster schieben das Ende nach hinten), wird der nächste wartende Task aktiv. `next` zuerst, geparkte (`pausiert`, `holding`, `inaktiv`) übersprungen, höchstens ein Wechsel, ohne aktive Tasks passiert nichts, mitten im Blocker auch nicht. Betrachtet wird nur die heutige Queue, vorgeplante Tage fasst der Tick nie an. Der Endpoint `POST /queue/tick` und die Hintergrund-Schleife (`app/tick.py`, `TICK_INTERVALL_SEKUNDEN`) rufen dieselbe Funktion.

**Wichtig:** die Schleife läuft im Lifespan. Bei mehreren Uvicorn-Workern liefe sie mehrfach, das Deployment nutzt deshalb bewusst **einen Worker**.

### Zeitzonen-Konvention

Die App rechnet fachlich in **lokaler, naiver Zeit** (TimeBlocks, TaskPhases, „heute", Tagesfenster, Export-Wochen). Zwei Sorten Timestamps, zwei Regeln:

- **Python-seitig geschriebene Zeiten** (TimeBlock, TaskPhase): naive lokale Werte. Postgres hängt beim Lesen nur ein Session-TZ-Label an, der Wert bleibt wie geschrieben → Label **abstreifen, nie konvertieren** (`_phasenzeit`, `_ohne_tz`, `replace(tzinfo=None)`).
- **Server-Defaults und echte UTC-Spalten** (`erstellt_am`, `erledigt_am`): echtes UTC → über `_lokal()` in lokale Zeit **konvertieren**.

Deshalb braucht der Container `TZ` (Default im Compose `Europe/Berlin`), sonst kippt „heute" um 22 Uhr. Und deshalb laufen die Tests zusätzlich zum SQLite-Setup einmal im Docker-Stack gegen Postgres, bevor etwas als fertig gilt: SQLite gibt naive Werte zurück und übersieht aware/naive-Mischfehler.

### API

Alle Routen unter `/api`, dazu `GET /health`. Kurzüberblick:

| Bereich | Endpunkte |
|---|---|
| Tasks | `GET /tasks?datum=` (Tages-Queue, Default heute; `erledigt=true` = globales Archiv), `POST /tasks` (+ `geplant_am`), `GET/PATCH/DELETE /tasks/{id}` (PATCH `geplant_am` verschiebt ans Ende des Zieltags), `PUT/DELETE /tasks/{id}/tags/{tag}`, `POST /tasks/{id}/erledigt` (optional `{zeitpunkt}` retro), `DELETE /tasks/{id}/erledigt` (→ heute, hinten), `GET /tasks/{id}/historie` |
| Phasen | `GET /phasen?datum=` (alle Phasen des Tages mit Task-Kontext), `POST /tasks/{id}/phasen` (nachtragen, `bis` Pflicht, keine Überlappung je Task), `PATCH/DELETE /phasen/{id}` (offene Phase schließen/löschen nimmt das aktiv-Tag mit runter) |
| Queue | `PUT /queue/order` (Ziel-Reihenfolge eines Tages, `datum` Default heute), `POST /queue/tick` (Rollover + Übergabe + heutige Liste), `POST /queue/feierabend` |
| Zeitblöcke | `GET/POST /timeblocks`, `PUT/DELETE /timeblocks/{id}` |
| Arbeitszeit | `GET/PUT /schedule`, `GET /capacity?datum=` |
| Export | `GET /export?woche=JJJJ-WXX` |

Interaktive Doku wie bei FastAPI üblich unter `/docs`.

## Frontend

SPA ohne Router, `App.tsx` hält den Zustand (inkl. des angezeigten Tages) und lädt alles über `api.ts`. Heute lädt über `POST /queue/tick` mit 30s-Polling, andere Tage lesen nur (`GET /tasks` + `/capacity` + `/phasen` mit `datum`). Komponenten:

- `Tagesleiste.tsx`: der Zeitstrahl, gerendert aus den Phasen des Tages. Drei Modi: `heute` (Jetzt-Linie, laufende Balken, Warteliste ab jetzt), `zukunft` (Warteliste ab Arbeitsfenster-Beginn), `vergangen` (nur Phasen, Klick öffnet den Phasen-Editor). Achsen-Layout, Ebenen, Blocker-Splitting, Dauer-Ziehen, Scrollen. Die mit Abstand komplexeste Komponente.
- `DateNav.tsx`: ‹ Datum › plus Heute-Knopf.
- `PhaseModal.tsx`: Phase bearbeiten/löschen/nachtragen (eigene Datumsfelder für Mitternachts-Spanner).
- `TaskDetail.tsx`: Task-Modal mit Geplant-am, Phasenliste, retro Erledigen und Tag-Historie.
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
