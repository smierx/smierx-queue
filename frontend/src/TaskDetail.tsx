import { useEffect, useState } from "react";

import { api } from "./api";
import { PhaseModal } from "./PhaseModal";
import type { Phase, TagEvent, Task } from "./types";

function phasenText(von: string, bis: string | null): string {
  const format: Intl.DateTimeFormatOptions = {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  };
  const anfang = new Date(von).toLocaleString("de-DE", format);
  if (bis === null) return `${anfang} – läuft`;
  return `${anfang} – ${new Date(bis).toLocaleString("de-DE", format)}`;
}

function jetztLokal(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(
    d.getMinutes(),
  )}`;
}

export function TaskDetail({ task, onClose, onChange }: {
  task: Task;
  onClose: () => void;
  onChange: () => void;
}) {
  const [titel, setTitel] = useState(task.titel);
  const [beschreibung, setBeschreibung] = useState(task.beschreibung);
  const [dauer, setDauer] = useState(String(task.dauer_minuten));
  const [geplantAm, setGeplantAm] = useState(task.geplant_am);
  const [erledigtUm, setErledigtUm] = useState(jetztLokal());
  const [historie, setHistorie] = useState<TagEvent[]>([]);
  const [phaseEdit, setPhaseEdit] = useState<Phase | null>(null);

  useEffect(() => {
    api.historie(task.id).then(setHistorie);
  }, [task.id]);

  async function speichern(event: React.FormEvent) {
    event.preventDefault();
    const dauerMinuten = Math.min(Math.max(Number(dauer) || 60, 5), 24 * 60);
    await api.taskAendern(task.id, {
      titel,
      beschreibung,
      dauer_minuten: dauerMinuten,
      geplant_am: geplantAm !== task.geplant_am ? geplantAm : undefined,
    });
    onChange();
    onClose();
  }

  async function retroErledigen() {
    if (!erledigtUm) return;
    await api.erledigen(task.id, `${erledigtUm}:00`);
    onChange();
    onClose();
  }

  async function phaseLoeschen(phasenId: number | null) {
    if (phasenId === null) return;
    await api.phaseLoeschen(phasenId);
    onChange();
    onClose();
  }

  return (
    <div className="modal-hintergrund" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <form onSubmit={speichern}>
          <label>
            Titel
            <input value={titel} onChange={(e) => setTitel(e.target.value)} />
          </label>
          <label>
            Beschreibung
            <textarea
              value={beschreibung}
              onChange={(e) => setBeschreibung(e.target.value)}
              rows={5}
            />
          </label>
          <div className="zeit-zeile">
            <label>
              Dauer (Minuten)
              <input
                type="number"
                min={5}
                max={24 * 60}
                step={5}
                value={dauer}
                onChange={(e) => setDauer(e.target.value)}
              />
            </label>
            {task.erledigt_am === null && (
              <label>
                Geplant am
                <input
                  type="date"
                  value={geplantAm}
                  onChange={(e) => e.target.value && setGeplantAm(e.target.value)}
                />
              </label>
            )}
          </div>
          <div className="modal-aktionen">
            <button type="button" className="sekundaer" onClick={onClose}>
              Abbrechen
            </button>
            <button type="submit">Speichern</button>
          </div>
        </form>

        {task.aktiv_phasen.length > 0 && (
          <>
            <h3>Phasen</h3>
            <ul className="historie">
              {task.aktiv_phasen.map((phase, i) => (
                <li key={phase.id ?? i}>
                  {phasenText(phase.von, phase.bis)}{" "}
                  <button
                    type="button"
                    className="sekundaer"
                    onClick={() =>
                      phase.id !== null &&
                      setPhaseEdit({
                        id: phase.id, task_id: task.id, titel: task.titel,
                        tags: task.tags, von: phase.von, bis: phase.bis,
                      })
                    }
                  >
                    Bearbeiten
                  </button>{" "}
                  <button
                    type="button"
                    className="loeschen"
                    aria-label="Phase löschen"
                    onClick={() => phaseLoeschen(phase.id)}
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}

        {task.erledigt_am === null && (
          <>
            <h3>Nachtragen</h3>
            <div className="zeit-zeile">
              <label>
                Erledigt am
                <input
                  type="datetime-local"
                  value={erledigtUm}
                  onChange={(e) => setErledigtUm(e.target.value)}
                />
              </label>
              <button type="button" className="sekundaer" onClick={retroErledigen}>
                Erledigt setzen
              </button>
            </div>
          </>
        )}

        <h3>Tag-Historie</h3>
        {historie.length === 0 && <p className="leer">Noch keine Tag-Änderungen.</p>}
        <ul className="historie">
          {historie.map((eintrag, i) => (
            <li key={i}>
              <span className={`tag an ${eintrag.tag}`}>{eintrag.tag}</span>{" "}
              {eintrag.aktion === "gesetzt" ? "gesetzt" : "entfernt"}{" "}
              <small>{new Date(eintrag.zeitpunkt).toLocaleString("de-DE")}</small>
            </li>
          ))}
        </ul>

        {phaseEdit && (
          <PhaseModal
            phase={phaseEdit}
            datum={task.geplant_am}
            onClose={() => setPhaseEdit(null)}
            onChange={() => {
              onChange();
              onClose();
            }}
          />
        )}
      </div>
    </div>
  );
}
