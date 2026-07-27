import { useCallback, useEffect, useState } from "react";

import { api } from "./api";
import { DateNav, datumLabel, heuteIso } from "./DateNav";
import { PhaseModal } from "./PhaseModal";
import { SchedulePanel } from "./SchedulePanel";
import { Tagesleiste, type LeistenModus } from "./Tagesleiste";
import { TaskDetail } from "./TaskDetail";
import {
  ALLE_TAGS,
  BEREICHE,
  type Bereich,
  type Capacity,
  type Phase,
  type Tag,
  type Task,
} from "./types";

const BEREICH_NAMEN: Record<Bereich, string> = { arbeit: "Arbeit", privat: "Privat" };

function gespeicherterBereich(): Bereich {
  return localStorage.getItem("queue.bereich") === "privat" ? "privat" : "arbeit";
}

function minutenAlsText(minuten: number): string {
  const h = Math.floor(minuten / 60);
  const m = minuten % 60;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}

function aktuelleWoche(): string {
  // ISO-Woche: der Donnerstag der Woche bestimmt Jahr und Nummer.
  const d = new Date();
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7));
  const jahresanfang = Date.UTC(t.getUTCFullYear(), 0, 1);
  const woche = Math.ceil(((t.getTime() - jahresanfang) / 86_400_000 + 1) / 7);
  return `${t.getUTCFullYear()}-W${String(woche).padStart(2, "0")}`;
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
  const [datum, setDatum] = useState(heuteIso());
  const [bereich, setBereich] = useState<Bereich>(gespeicherterBereich);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [phasen, setPhasen] = useState<Phase[]>([]);
  const [erledigte, setErledigte] = useState<Task[]>([]);
  const [archivOffen, setArchivOffen] = useState(false);
  const [kapazitaet, setKapazitaet] = useState<Capacity | null>(null);
  const [neuerTitel, setNeuerTitel] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [detail, setDetail] = useState<Task | null>(null);
  // null = zu, { phase: null } = neue Phase nachtragen, sonst bearbeiten.
  const [phaseModal, setPhaseModal] = useState<{ phase: Phase | null } | null>(null);
  const [dragId, setDragId] = useState<number | null>(null);
  const [exportWoche, setExportWoche] = useState(aktuelleWoche());

  const istHeute = datum === heuteIso();
  const modus: LeistenModus = istHeute ? "heute" : datum < heuteIso() ? "vergangen" : "zukunft";

  const laden = useCallback(async () => {
    try {
      // Heute übernimmt der Tick Rollover und Statuswechsel und liefert die
      // Liste, andere Tage werden nur gelesen. Die Phasen füttern den Zeitstrahl.
      const [t, k, p] = await Promise.all([
        datum === heuteIso() ? api.queueTick(bereich) : api.tasks(bereich, datum),
        api.kapazitaet(bereich, datum),
        api.phasen(bereich, datum),
      ]);
      setTasks(t);
      setKapazitaet(k);
      setPhasen(p);
      setFehler(null);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    }
  }, [datum, bereich]);

  const ladenArchiv = useCallback(async () => {
    try {
      setErledigte(await api.tasksErledigt(bereich));
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    }
  }, [bereich]);

  function bereichWechseln(neu: Bereich) {
    if (neu === bereich) return;
    localStorage.setItem("queue.bereich", neu);
    // Offene Modals zeigen sonst Objekte der anderen Seite.
    setDetail(null);
    setPhaseModal(null);
    setBereich(neu);
  }

  useEffect(() => {
    laden();
    if (!istHeute) return;
    // Polling hält Jetzt-Linie und automatischen Statuswechsel am Laufen, nur heute.
    const timer = setInterval(laden, 30_000);
    return () => clearInterval(timer);
  }, [laden, istHeute]);

  useEffect(() => {
    if (archivOffen) ladenArchiv();
  }, [archivOffen, ladenArchiv]);

  async function anlegen(event: React.FormEvent) {
    event.preventDefault();
    if (!neuerTitel.trim()) return;
    await api.taskAnlegen(neuerTitel.trim(), bereich, istHeute ? undefined : datum);
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
    if (archivOffen) ladenArchiv();
  }

  async function exportieren() {
    if (!exportWoche) return;
    const daten = await api.exportWoche(exportWoche, bereich);
    const blob = new Blob([JSON.stringify(daten, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `smierx-queue-${bereich}-${exportWoche}.json`;
    a.click();
    URL.revokeObjectURL(url);
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
    await api.umsortieren([...aktive.map((t) => t.id), ...angezeigt], bereich, datum);
    laden();
  }

  return (
    <div className="wrap" data-bereich={bereich}>
      <header>
        <h1>
          smierx<span>-queue</span>
        </h1>
        <div className="bereich-toggle" role="group" aria-label="Bereich wechseln">
          {BEREICHE.map((b) => (
            <button
              key={b}
              type="button"
              className={b === bereich ? "an" : ""}
              onClick={() => bereichWechseln(b)}
            >
              {BEREICH_NAMEN[b]}
            </button>
          ))}
        </div>
        {kapazitaet && (
          <div className="kapazitaet">
            {datumLabel(datum)} {minutenAlsText(kapazitaet.frei_minuten)} frei
            <small>
              {minutenAlsText(kapazitaet.arbeitszeit_minuten)} Arbeitszeit,{" "}
              {minutenAlsText(kapazitaet.geblockt_minuten)} geblockt
            </small>
          </div>
        )}
      </header>

      {fehler && <p className="fehler">API nicht erreichbar: {fehler}</p>}

      <section>
        <h2>
          {datumLabel(datum)}
          <DateNav datum={datum} onChange={setDatum} />
        </h2>
        {modus === "vergangen" && (
          <p className="hint">
            Vergangener Tag: Phasen im Zeitstrahl anklicken zum Korrigieren, Blocker nachtragen.
          </p>
        )}
        {kapazitaet && (
          <Tagesleiste
            datum={datum}
            bereich={bereich}
            modus={modus}
            kapazitaet={kapazitaet}
            phasen={phasen}
            aktive={aktive}
            geplante={queue}
            onChange={laden}
            onTaskClick={setDetail}
            onPhaseClick={(phase) => setPhaseModal({ phase })}
            onPhaseNeu={() => setPhaseModal({ phase: null })}
          />
        )}
      </section>

      <SchedulePanel bereich={bereich} onChange={laden} />

      {istHeute && (
        <section>
          <h2>
            Läuft gerade
            {aktive.length > 0 && (
              <button
                type="button"
                className="sekundaer h2-aktion"
                title="Alle aktiven Tasks auf next setzen"
                onClick={() => api.feierabend(bereich).then(laden)}
              >
                🌙 Feierabend
              </button>
            )}
          </h2>
          {aktive.length === 0 && (
            <p className="leer">Nichts aktiv. Zieh dir was aus der Queue.</p>
          )}
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
      )}

      <section>
        <h2>
          Queue für {datumLabel(datum)}{" "}
          <span className="hint">next zuerst · ziehen zum Umsortieren</span>
        </h2>
        {queue.length === 0 && !istHeute && (
          <p className="leer">
            {modus === "zukunft" ? "Noch nichts geplant für diesen Tag." : "Hier lag nichts mehr."}
          </p>
        )}
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
            placeholder={istHeute ? "Neuer Task…" : `Neuer Task für ${datumLabel(datum)}…`}
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
                  onClick={() =>
                    api.wiederOeffnen(task.id).then(() => {
                      laden();
                      ladenArchiv();
                    })
                  }
                >
                  Wieder öffnen
                </button>
                <button
                  type="button"
                  className="loeschen"
                  aria-label="endgültig löschen"
                  onClick={() =>
                    api.taskLoeschen(task.id).then(() => {
                      laden();
                      ladenArchiv();
                    })
                  }
                >
                  ✕
                </button>
              </article>
            ))
          ))}
      </section>

      <section>
        <h2>Export</h2>
        <div className="export-zeile">
          <input
            type="week"
            value={exportWoche}
            onChange={(e) => setExportWoche(e.target.value)}
          />
          <button type="button" className="sekundaer" onClick={exportieren}>
            Woche als JSON exportieren
          </button>
          <span className="hint">aktiv-Phasen, Erledigtes und Blocker der Woche</span>
        </div>
      </section>

      {detail && <TaskDetail task={detail} onClose={() => setDetail(null)} onChange={laden} />}
      {phaseModal && (
        <PhaseModal
          phase={phaseModal.phase}
          datum={datum}
          bereich={bereich}
          onClose={() => setPhaseModal(null)}
          onChange={laden}
        />
      )}
    </div>
  );
}
