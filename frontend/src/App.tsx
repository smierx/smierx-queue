import { useCallback, useEffect, useState } from "react";

import { api } from "./api";
import { GitLabPanel } from "./GitLabPanel";
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
  const [kapazitaet, setKapazitaet] = useState<Capacity | null>(null);
  const [neuerTitel, setNeuerTitel] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [detail, setDetail] = useState<Task | null>(null);
  const [dragId, setDragId] = useState<number | null>(null);

  const laden = useCallback(async () => {
    try {
      const [t, k] = await Promise.all([api.tasks(), api.kapazitaet()]);
      setTasks(t);
      setKapazitaet(k);
      setFehler(null);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    laden();
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

  async function abgelegt(zielId: number) {
    if (dragId === null || dragId === zielId) return;
    const ids = tasks.map((t) => t.id).filter((id) => id !== dragId);
    ids.splice(ids.indexOf(zielId), 0, dragId);
    setDragId(null);
    await api.umsortieren(ids);
    laden();
  }

  const aktive = tasks.filter((t) => t.tags.includes("aktiv"));
  const queue = tasks.filter((t) => !t.tags.includes("aktiv"));

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
        {kapazitaet && <Tagesleiste kapazitaet={kapazitaet} onChange={laden} />}
      </section>

      <section>
        <h2>Läuft gerade</h2>
        {aktive.length === 0 && <p className="leer">Nichts aktiv. Zieh dir was aus der Queue.</p>}
        {aktive.map((task) => (
          <article
            key={task.id}
            className={`karte ${task.tags.includes("critical") ? "critical" : ""}`}
          >
            <button type="button" className="titel-knopf" onClick={() => setDetail(task)}>
              {task.titel}
            </button>
            <TagChips task={task} onToggle={(tag) => tagToggle(task, tag)} />
          </article>
        ))}
      </section>

      <section>
        <h2>
          Queue <span className="hint">ziehen zum Umsortieren, Titel klicken für Details</span>
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
              className="loeschen"
              onClick={() => api.taskLoeschen(task.id).then(laden)}
              aria-label="löschen"
            >
              ✕
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

      <GitLabPanel onSynced={laden} />

      {detail && <TaskDetail task={detail} onClose={() => setDetail(null)} onChange={laden} />}
    </div>
  );
}
