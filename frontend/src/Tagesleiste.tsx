import { useState } from "react";

import { api } from "./api";
import type { Capacity, TimeBlock } from "./types";

function minuten(iso: string): number {
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes();
}

function alsZeit(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function heuteUm(zeit: string): string {
  const jetzt = new Date();
  const heute = `${jetzt.getFullYear()}-${String(jetzt.getMonth() + 1).padStart(2, "0")}-${String(
    jetzt.getDate(),
  ).padStart(2, "0")}`;
  return `${heute}T${zeit}:00`;
}

function jetztZeit(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function zeitPlus(zeit: string, plusMinuten: number): string {
  const [h, m] = zeit.split(":").map(Number);
  const gesamt = Math.min(h * 60 + m + plusMinuten, 23 * 60 + 59);
  return `${String(Math.floor(gesamt / 60)).padStart(2, "0")}:${String(gesamt % 60).padStart(2, "0")}`;
}

interface FormDaten {
  id: number | null; // null = neu anlegen
  titel: string;
  typ: "meeting" | "blocker";
  von: string;
  bis: string;
}

export function Tagesleiste({ kapazitaet, onChange }: { kapazitaet: Capacity; onChange: () => void }) {
  const [form, setForm] = useState<FormDaten | null>(null);

  // Rahmen: feste Zeiten aus dem Arbeitszeit-Modell, im Stunden-Modus 07 bis 16 Uhr.
  // Blöcke außerhalb weiten die Achse, damit nichts unsichtbar bleibt.
  let achseStart = 7 * 60;
  let achseEnde = 16 * 60;
  if (kapazitaet.fenster_von && kapazitaet.fenster_bis) {
    const [vh, vm] = kapazitaet.fenster_von.split(":").map(Number);
    const [bh, bm] = kapazitaet.fenster_bis.split(":").map(Number);
    achseStart = vh * 60 + vm;
    achseEnde = bh * 60 + bm;
  }
  for (const block of kapazitaet.bloecke) {
    achseStart = Math.min(achseStart, minuten(block.start));
    achseEnde = Math.max(achseEnde, minuten(block.ende));
  }
  achseStart = Math.floor(achseStart / 60) * 60;
  achseEnde = Math.ceil(achseEnde / 60) * 60;
  const spanne = achseEnde - achseStart;
  const stunden = Array.from({ length: spanne / 60 }, (_, i) => achseStart / 60 + i);

  const jetzt = new Date();
  const jetztMin = jetzt.getHours() * 60 + jetzt.getMinutes();

  function bearbeiten(block: TimeBlock) {
    setForm({
      id: block.id,
      titel: block.titel,
      typ: block.typ,
      von: alsZeit(block.start),
      bis: alsZeit(block.ende),
    });
  }

  async function spontanBlocker() {
    // Ein Klick: Blocker ab jetzt für 30 Minuten. Details danach anpassbar.
    const von = jetztZeit();
    const block = await api.timeblockAnlegen({
      titel: "Unterbrechung",
      typ: "blocker",
      start: heuteUm(von),
      ende: heuteUm(zeitPlus(von, 30)),
    });
    onChange();
    bearbeiten(block);
  }

  async function speichern(event: React.FormEvent) {
    event.preventDefault();
    if (!form || !form.titel.trim()) return;
    const daten = {
      titel: form.titel.trim(),
      typ: form.typ,
      start: heuteUm(form.von),
      ende: heuteUm(form.bis),
    };
    if (form.id === null) await api.timeblockAnlegen(daten);
    else await api.timeblockAendern(form.id, daten);
    setForm(null);
    onChange();
  }

  async function loeschen() {
    if (form?.id != null) {
      await api.timeblockLoeschen(form.id);
      setForm(null);
      onChange();
    }
  }

  return (
    <div className="tagesleiste">
      <div className="achse">
        {stunden.map((h) => (
          <div key={h} className="stunde">
            <small>{String(h).padStart(2, "0")}</small>
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
              title={`${block.titel} – klicken zum Bearbeiten`}
              onClick={() => bearbeiten(block)}
            >
              {block.titel}
            </button>
          );
        })}
        {jetztMin >= achseStart && jetztMin <= achseEnde && (
          <div className="jetzt" style={{ left: `${((jetztMin - achseStart) / spanne) * 100}%` }} />
        )}
      </div>
      <div className="leiste-fuss">
        <button type="button" className="spontan" onClick={spontanBlocker}>
          ⚡ Blocker jetzt
        </button>
        <button
          type="button"
          className="sekundaer"
          onClick={() =>
            setForm(
              form
                ? null
                : { id: null, titel: "", typ: "meeting", von: "09:00", bis: "10:00" },
            )
          }
        >
          + Termin/Blocker
        </button>
      </div>
      {form && (
        <form onSubmit={speichern} className="block-form">
          <input
            value={form.titel}
            onChange={(e) => setForm({ ...form, titel: e.target.value })}
            placeholder="Titel"
          />
          <select
            value={form.typ}
            onChange={(e) => setForm({ ...form, typ: e.target.value as "meeting" | "blocker" })}
          >
            <option value="meeting">Meeting</option>
            <option value="blocker">Blocker</option>
          </select>
          <input
            type="time"
            value={form.von}
            onChange={(e) => setForm({ ...form, von: e.target.value })}
          />
          <input
            type="time"
            value={form.bis}
            onChange={(e) => setForm({ ...form, bis: e.target.value })}
          />
          {form.id !== null && (
            <button
              type="button"
              className="sekundaer"
              title="Endzeit auf jetzt setzen"
              onClick={() => setForm({ ...form, bis: jetztZeit() })}
            >
              Bis jetzt
            </button>
          )}
          <button type="submit">{form.id === null ? "Eintragen" : "Speichern"}</button>
          {form.id !== null && (
            <button type="button" className="sekundaer" onClick={loeschen}>
              Löschen
            </button>
          )}
        </form>
      )}
    </div>
  );
}
