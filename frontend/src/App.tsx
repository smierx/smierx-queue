import { useCallback, useEffect, useState } from "react";

import { api } from "./api";
import { GitLabPanel } from "./GitLabPanel";
import { SchedulePanel } from "./SchedulePanel";
import { Tagesleiste } from "./Tagesleiste";
import { TaskDetail } from "./TaskDetail";
import { ALLE_TAGS, type Capacity, type Tag, type Task } from "./types";

function minutenAlsText(minuten: number): string {
  const h = Math.floor(minuten / 60);
  const m = minuten % 60;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}

function TagChips({ task, onToggle }: { task: Task; onToggle: (tag: Tag) => void }) {
  return (
    <span className="tagrow">
      {ALLE_TAGS.map((tag) => (
        <button
          key={tag}
          type="button"
          className={`tag ${tag} ${task.tags.includes(tag) ? "an" : "aus"}`}
          onClick={() => onToggle(tag)}
        >
          {tag}
        </button>
      ))}
    </span>
  );
}

export default function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [erledigte, setErledigte] = useState<Task[]>([]);
  const [archivOffen, setArchivOffen] = useState(false);
  const [kapazitaet, setKapazitaet] = useState<Capacity | null>(null);
  const [neuerTitel, setNeuerTitel] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [detail, setDetail] = useState<Task | null>(null);
  const [dragId, setDragId] = useState<number | null>(null);

  const laden = useCallback(async () => {
    try {
      // Der Tick übernimmt den automatischen Statuswechsel und liefert die Liste.
      // Erledigte braucht der Zeitstrahl immer: ihre aktiv-Phasen bleiben stehen.
      const [t, k, e] = await Promise.all([
        api.queueTick(),
        api.kapazitaet(),
        api.tasksErledigt(),
      ]);
      setTasks(t);
      setKapazitaet(k);
      setErledigte(e);
      setFehler(null);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    laden();
    // Polling hält Jetzt-Linie und automatischen Statuswechsel am Laufen.
    const timer = setInterval(laden, 30_000);
    return () => clearInterval(timer);
  }, [laden]);

  async function anlegen(event: React.FormEvent) {
    event.preventDefault();
    if (!neuerTitel.trim()) return;
    await api.taskAnlegen(neuerTitel.trim());
    setNeuerTitel("");
    laden();
  }

  async function tagToggle(task: Task, tag: Tag) {
    if (task.tags.includes(tag)) await api.tagEntfernen(task.id, tag);
    else await api.tagSetzen(task.id, tag);
    laden();
  }

  async function erledigen(task: Task) {
    await api.erledigen(task.id);
    laden();
  }

  const aktive = tasks.filter((t) => t.tags.includes("aktiv"));
  // Queue-Anzeige: next zuerst, dahinter der Rest, innerhalb der Gruppen nach Position.
  const queue = tasks
    .filter((t) => !t.tags.includes("aktiv"))
    .sort((a, b) => {
      const rangA = a.tags.includes("next") ? 0 : 1;
      const rangB = b.tags.includes("next") ? 0 : 1;
      return rangA - rangB || a.position - b.position;
    });

  async function abgelegt(zielId: number) {
    if (dragId === null || dragId === zielId) return;
    // Neue Reihenfolge aus der angezeigten Queue ableiten, aktive Tasks bleiben vorn.
    const angezeigt = queue.map((t) => t.id).filter((id) => id !== dragId);
    angezeigt.splice(angezeigt.indexOf(zielId), 0, dragId);
    setDragId(null);
    await api.umsortieren([...aktive.map((t) => t.id), ...angezeigt]);
    laden();
  }

  return (
    <div className="wrap">
      <header>
        <h1>
          smierx<span>-queue</span>
        </h1>
        {kapazitaet && (
          <div className="kapazitaet">
            heute {minutenAlsText(kapazitaet.frei_minuten)} frei
            <small>
              {minutenAlsText(kapazitaet.arbeitszeit_minuten)} Arbeitszeit,{" "}
              {minutenAlsText(kapazitaet.geblockt_minuten)} geblockt
            </small>
          </div>
        )}
      </header>

      {fehler && <p className="fehler">API nicht erreichbar: {fehler}</p>}

      <section>
        <h2>Heute</h2>
        {kapazitaet && (
          <Tagesleiste
            kapazitaet={kapazitaet}
            aktive={aktive}
            geplante={queue}
            erledigte={erledigte}
            onChange={laden}
            onTaskClick={setDetail}
          />
        )}
      </section>

      <SchedulePanel onChange={laden} />

      <section>
        <h2>
          Läuft gerade
          {aktive.length > 0 && (
            <button
              type="button"
              className="sekundaer h2-aktion"
              title="Alle aktiven Tasks auf next setzen"
              onClick={() => api.feierabend().then(laden)}
            >
              🌙 Feierabend
            </button>
          )}
        </h2>
        {aktive.length === 0 && <p className="leer">Nichts aktiv. Zieh dir was aus der Queue.</p>}
        {aktive.map((task) => (
          <article
            key={task.id}
            className={`karte ${task.tags.includes("critical") ? "critical" : ""}`}
          >
            <div className="karten-kopf">
              <button type="button" className="titel-knopf" onClick={() => setDetail(task)}>
                {task.titel}
              </button>
              <button
                type="button"
                className="fertig"
                title="Erledigt"
                onClick={() => erledigen(task)}
              >
                ✓
              </button>
            </div>
            <TagChips task={task} onToggle={(tag) => tagToggle(task, tag)} />
          </article>
        ))}
      </section>

      <section>
        <h2>
          Queue <span className="hint">next zuerst · ziehen zum Umsortieren</span>
        </h2>
        {queue.map((task) => (
          <article
            key={task.id}
            className={`zeile ${dragId === task.id ? "am-ziehen" : ""}`}
            draggable
            onDragStart={() => setDragId(task.id)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => abgelegt(task.id)}
            onDragEnd={() => setDragId(null)}
          >
            <span className="grip" aria-hidden>
              ⠿
            </span>
            <button type="button" className="titel-knopf" onClick={() => setDetail(task)}>
              {task.titel}
            </button>
            <TagChips task={task} onToggle={(tag) => tagToggle(task, tag)} />
            <button
              type="button"
              className="fertig"
              title="Erledigt"
              onClick={() => erledigen(task)}
            >
              ✓
            </button>
          </article>
        ))}
        <form onSubmit={anlegen} className="neu">
          <input
            value={neuerTitel}
            onChange={(e) => setNeuerTitel(e.target.value)}
            placeholder="Neuer Task…"
          />
          <button type="submit">In die Queue</button>
        </form>
      </section>

      <section>
        <h2>
          <button type="button" className="aufklappen" onClick={() => setArchivOffen(!archivOffen)}>
            Erledigt {archivOffen ? "▾" : "▸"}
          </button>
        </h2>
        {archivOffen &&
          (erledigte.length === 0 ? (
            <p className="leer">Noch nichts erledigt.</p>
          ) : (
            erledigte.map((task) => (
              <article key={task.id} className="zeile erledigt">
                <span className="titel">{task.titel}</span>
                <small>
                  {task.erledigt_am && new Date(task.erledigt_am).toLocaleString("de-DE")}
                </small>
                <button
                  type="button"
                  className="sekundaer"
                  onClick={() => api.wiederOeffnen(task.id).then(laden)}
                >
                  Wieder öffnen
                </button>
                <button
                  type="button"
                  className="loeschen"
                  aria-label="endgültig löschen"
                  onClick={() => api.taskLoeschen(task.id).then(laden)}
                >
                  ✕
                </button>
              </article>
            ))
          ))}
      </section>

      <GitLabPanel onSynced={laden} />

      {detail && <TaskDetail task={detail} onClose={() => setDetail(null)} onChange={laden} />}
    </div>
  );
}
