import { useEffect, useState } from "react";

import { api } from "./api";
import type { Bereich, Phase, Task } from "./types";

function alsDatum(iso: string): string {
  return iso.slice(0, 10);
}

function alsZeit(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

// Bearbeitet eine Phase oder trägt eine neue nach (phase = null). Von/Bis haben
// eigene Datumsfelder, damit Phasen über Mitternacht nicht kaputtgehen.
export function PhaseModal({ phase, datum, bereich, onClose, onChange }: {
  phase: Phase | null;
  datum: string; // Vorbelegung fürs Nachtragen (YYYY-MM-DD)
  bereich?: Bereich; // schränkt die Task-Auswahl beim Nachtragen ein
  onClose: () => void;
  onChange: () => void;
}) {
  const neu = phase === null;
  const [taskId, setTaskId] = useState<string>(phase ? String(phase.task_id) : "");
  const [taskListe, setTaskListe] = useState<Task[]>([]);
  const [vonDatum, setVonDatum] = useState(phase ? alsDatum(phase.von) : datum);
  const [vonZeit, setVonZeit] = useState(phase ? alsZeit(phase.von) : "09:00");
  const [bisDatum, setBisDatum] = useState(
    phase ? (phase.bis ? alsDatum(phase.bis) : "") : datum,
  );
  const [bisZeit, setBisZeit] = useState(phase ? (phase.bis ? alsZeit(phase.bis) : "") : "10:00");
  const [fehler, setFehler] = useState<string | null>(null);
  const offen = phase !== null && phase.bis === null;

  useEffect(() => {
    if (!neu) return;
    // Kandidaten fürs Nachtragen: die heutige Queue plus das Archiv des Bereichs.
    const b = bereich ?? "arbeit";
    Promise.all([api.tasks(b), api.tasksErledigt(b)]).then(([offene, erledigte]) =>
      setTaskListe([...offene, ...erledigte]),
    );
  }, [neu, bereich]);

  async function speichern(event: React.FormEvent) {
    event.preventDefault();
    setFehler(null);
    const von = `${vonDatum}T${vonZeit}:00`;
    const bis = bisDatum && bisZeit ? `${bisDatum}T${bisZeit}:00` : null;
    try {
      if (neu) {
        if (!taskId || !bis) return;
        await api.phaseAnlegen(Number(taskId), { von, bis });
      } else if (bis !== null) {
        await api.phaseAendern(phase.id, { von, bis });
      } else {
        await api.phaseAendern(phase.id, { von });
      }
      onChange();
      onClose();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    }
  }

  async function loeschen() {
    if (neu) return;
    await api.phaseLoeschen(phase.id);
    onChange();
    onClose();
  }

  return (
    <div className="modal-hintergrund" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <form onSubmit={speichern}>
          <h3>{neu ? "Phase nachtragen" : `Phase: ${phase.titel}`}</h3>
          {neu && (
            <label>
              Task
              <select value={taskId} onChange={(e) => setTaskId(e.target.value)} required>
                <option value="" disabled>
                  Task wählen…
                </option>
                {taskListe.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.titel}
                    {t.erledigt_am ? " (erledigt)" : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="zeit-zeile">
            <label>
              Von
              <input
                type="date"
                value={vonDatum}
                onChange={(e) => setVonDatum(e.target.value)}
                required
              />
            </label>
            <label>
              &nbsp;
              <input
                type="time"
                value={vonZeit}
                onChange={(e) => setVonZeit(e.target.value)}
                required
              />
            </label>
          </div>
          <div className="zeit-zeile">
            <label>
              Bis
              <input
                type="date"
                value={bisDatum}
                onChange={(e) => setBisDatum(e.target.value)}
                required={!offen}
              />
            </label>
            <label>
              &nbsp;
              <input
                type="time"
                value={bisZeit}
                onChange={(e) => setBisZeit(e.target.value)}
                required={!offen}
              />
            </label>
          </div>
          {offen && (
            <p className="hint">
              Die Phase läuft noch. Bis setzen schließt sie und beendet den Task (aktiv → next).
            </p>
          )}
          {fehler && <p className="fehler">{fehler}</p>}
          <div className="modal-aktionen">
            {!neu && (
              <button type="button" className="sekundaer" onClick={loeschen}>
                Löschen
              </button>
            )}
            <button type="button" className="sekundaer" onClick={onClose}>
              Abbrechen
            </button>
            <button type="submit">{neu ? "Nachtragen" : "Speichern"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}
