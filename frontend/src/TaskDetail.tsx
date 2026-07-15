import { useEffect, useState } from "react";

import { api } from "./api";
import type { TagEvent, Task } from "./types";

export function TaskDetail({ task, onClose, onChange }: {
  task: Task;
  onClose: () => void;
  onChange: () => void;
}) {
  const [titel, setTitel] = useState(task.titel);
  const [beschreibung, setBeschreibung] = useState(task.beschreibung);
  const [dauer, setDauer] = useState(String(task.dauer_minuten));
  const [historie, setHistorie] = useState<TagEvent[]>([]);

  useEffect(() => {
    api.historie(task.id).then(setHistorie);
  }, [task.id]);

  async function speichern(event: React.FormEvent) {
    event.preventDefault();
    const dauerMinuten = Math.min(Math.max(Number(dauer) || 60, 5), 24 * 60);
    await api.taskAendern(task.id, { titel, beschreibung, dauer_minuten: dauerMinuten });
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
          <div className="modal-aktionen">
            <button type="button" className="sekundaer" onClick={onClose}>
              Abbrechen
            </button>
            <button type="submit">Speichern</button>
          </div>
        </form>
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
      </div>
    </div>
  );
}
