import { useState } from "react";

import { api } from "./api";
import type { Capacity } from "./types";

function minuten(iso: string): number {
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes();
}

function heuteUm(zeit: string): string {
  const heute = new Date().toISOString().slice(0, 10);
  return `${heute}T${zeit}:00`;
}

export function Tagesleiste({ kapazitaet, onChange }: { kapazitaet: Capacity; onChange: () => void }) {
  const [formOffen, setFormOffen] = useState(false);
  const [titel, setTitel] = useState("");
  const [typ, setTyp] = useState<"meeting" | "blocker">("meeting");
  const [von, setVon] = useState("09:00");
  const [bis, setBis] = useState("10:00");

  // Achse: 08:00 bis 18:00, Blöcke außerhalb werden geclippt.
  const achseStart = 8 * 60;
  const achseEnde = 18 * 60;
  const spanne = achseEnde - achseStart;
  const jetzt = minuten(new Date().toISOString().slice(0, 19));

  async function anlegen(event: React.FormEvent) {
    event.preventDefault();
    if (!titel.trim()) return;
    await api.timeblockAnlegen({ titel: titel.trim(), typ, start: heuteUm(von), ende: heuteUm(bis) });
    setTitel("");
    setFormOffen(false);
    onChange();
  }

  return (
    <div className="tagesleiste">
      <div className="achse">
        {Array.from({ length: 11 }, (_, i) => (
          <div key={i} className="stunde">
            <small>{String(8 + i).padStart(2, "0")}</small>
          </div>
        ))}
        {kapazitaet.bloecke.map((block) => {
          const start = Math.max(minuten(block.start), achseStart);
          const ende = Math.min(minuten(block.ende), achseEnde);
          if (ende <= start) return null;
          return (
            <button
              key={block.id}
              type="button"
              className={`block ${block.typ}`}
              style={{
                left: `${((start - achseStart) / spanne) * 100}%`,
                width: `${((ende - start) / spanne) * 100}%`,
              }}
              title={`${block.titel} – klicken zum Löschen`}
              onClick={() => api.timeblockLoeschen(block.id).then(onChange)}
            >
              {block.titel}
            </button>
          );
        })}
        {jetzt >= achseStart && jetzt <= achseEnde && (
          <div className="jetzt" style={{ left: `${((jetzt - achseStart) / spanne) * 100}%` }} />
        )}
      </div>
      <div className="leiste-fuss">
        <button type="button" className="sekundaer" onClick={() => setFormOffen(!formOffen)}>
          + Termin/Blocker
        </button>
      </div>
      {formOffen && (
        <form onSubmit={anlegen} className="block-form">
          <input value={titel} onChange={(e) => setTitel(e.target.value)} placeholder="Titel" />
          <select value={typ} onChange={(e) => setTyp(e.target.value as "meeting" | "blocker")}>
            <option value="meeting">Meeting</option>
            <option value="blocker">Blocker</option>
          </select>
          <input type="time" value={von} onChange={(e) => setVon(e.target.value)} />
          <input type="time" value={bis} onChange={(e) => setBis(e.target.value)} />
          <button type="submit">Eintragen</button>
        </form>
      )}
    </div>
  );
}
