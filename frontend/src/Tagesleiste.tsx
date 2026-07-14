import { useRef, useState } from "react";

import { api } from "./api";
import type { Capacity, Task, TimeBlock } from "./types";

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

export function Tagesleiste({ kapazitaet, aktive, onChange, onTaskClick }: {
  kapazitaet: Capacity;
  aktive: Task[];
  onChange: () => void;
  onTaskClick: (task: Task) => void;
}) {
  const [form, setForm] = useState<FormDaten | null>(null);
  // Verschiebung der Achse in Minuten relativ zum Auto-Fenster.
  const [offset, setOffset] = useState(0);
  const drag = useRef<{ x: number; offset: number; bewegt: boolean } | null>(null);

  const jetzt = new Date();
  const jetztMin = jetzt.getHours() * 60 + jetzt.getMinutes();
  const heuteStart = new Date(jetzt.getFullYear(), jetzt.getMonth(), jetzt.getDate());

  // Laufende Tasks: Balken von "aktiv gesetzt" bis jetzt. Start vor heute → ab Tagesanfang.
  const laufende = aktive
    .filter((t) => t.aktiv_seit !== null)
    .map((t) => ({
      task: t,
      startMin: new Date(t.aktiv_seit!) < heuteStart ? 0 : minuten(t.aktiv_seit!),
    }));

  // Auto-Fenster: feste Zeiten aus dem Arbeitszeit-Modell, im Stunden-Modus 07 bis 16 Uhr.
  // Blöcke und laufende Tasks außerhalb weiten das Fenster, damit nichts unsichtbar bleibt.
  let autoStart = 7 * 60;
  let autoEnde = 16 * 60;
  if (kapazitaet.fenster_von && kapazitaet.fenster_bis) {
    const [vh, vm] = kapazitaet.fenster_von.split(":").map(Number);
    const [bh, bm] = kapazitaet.fenster_bis.split(":").map(Number);
    autoStart = vh * 60 + vm;
    autoEnde = bh * 60 + bm;
  }
  for (const block of kapazitaet.bloecke) {
    autoStart = Math.min(autoStart, minuten(block.start));
    autoEnde = Math.max(autoEnde, minuten(block.ende));
  }
  for (const { startMin } of laufende) {
    if (startMin > 0) autoStart = Math.min(autoStart, startMin);
    autoEnde = Math.max(autoEnde, jetztMin);
  }
  autoStart = Math.floor(autoStart / 60) * 60;
  autoEnde = Math.ceil(autoEnde / 60) * 60;
  const spanne = autoEnde - autoStart;

  // Sichtfenster: Auto-Fenster plus Verschiebung, geklemmt auf 00:00 bis 24:00.
  const offsetMin = -autoStart;
  const offsetMax = 24 * 60 - spanne - autoStart;
  const klemmen = (wert: number) => Math.min(Math.max(wert, offsetMin), offsetMax);
  const viewStart = autoStart + klemmen(offset);
  const viewEnde = viewStart + spanne;

  const ticks: number[] = [];
  for (let h = Math.ceil(viewStart / 60); h * 60 <= viewEnde; h++) ticks.push(h);

  function position(vonMin: number, bisMin: number) {
    const start = Math.max(vonMin, viewStart);
    const ende = Math.min(bisMin, viewEnde);
    if (ende <= start) return null;
    return {
      left: `${((start - viewStart) / spanne) * 100}%`,
      width: `${((ende - start) / spanne) * 100}%`,
    };
  }

  // Ziehen zum Verschieben. Klicks auf Blöcke bleiben erhalten (Schwelle 5px),
  // nach echtem Ziehen wird der Klick unterdrückt.
  function pointerDown(e: React.PointerEvent<HTMLDivElement>) {
    drag.current = { x: e.clientX, offset: klemmen(offset), bewegt: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function pointerMove(e: React.PointerEvent<HTMLDivElement>) {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    if (Math.abs(dx) > 5) d.bewegt = true;
    if (d.bewegt) {
      const minutenProPixel = spanne / e.currentTarget.clientWidth;
      setOffset(klemmen(d.offset - dx * minutenProPixel));
    }
  }
  function pointerUp() {
    // bewegt-Flag kurz stehen lassen, damit der Click-Capture es noch sieht.
    setTimeout(() => (drag.current = null), 0);
  }
  function clickCapture(e: React.MouseEvent) {
    if (drag.current?.bewegt) {
      e.stopPropagation();
      e.preventDefault();
    }
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

  function bearbeiten(block: TimeBlock) {
    setForm({
      id: block.id,
      titel: block.titel,
      typ: block.typ,
      von: alsZeit(block.start),
      bis: alsZeit(block.ende),
    });
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
      <div
        className="achse"
        onPointerDown={pointerDown}
        onPointerMove={pointerMove}
        onPointerUp={pointerUp}
        onPointerCancel={pointerUp}
        onClickCapture={clickCapture}
        onWheel={(e) => setOffset(klemmen(offset + (e.deltaX || e.deltaY) * 0.5))}
      >
        {ticks.map((h) => (
          <div
            key={h}
            className="tick"
            style={{ left: `${((h * 60 - viewStart) / spanne) * 100}%` }}
          >
            <small>{String(h).padStart(2, "0")}</small>
          </div>
        ))}
        {kapazitaet.bloecke.map((block) => {
          const pos = position(minuten(block.start), minuten(block.ende));
          if (!pos) return null;
          return (
            <button
              key={block.id}
              type="button"
              className={`block ${block.typ}`}
              style={pos}
              title={`${block.titel} – klicken zum Bearbeiten`}
              onClick={() => bearbeiten(block)}
            >
              {block.titel}
            </button>
          );
        })}
        {laufende.map(({ task, startMin }) => {
          const pos = position(startMin, Math.max(jetztMin, startMin + 4));
          if (!pos) return null;
          return (
            <button
              key={`task-${task.id}`}
              type="button"
              className="block task"
              style={pos}
              title={`${task.titel} – läuft seit ${startMin === 0 ? "gestern oder früher" : alsZeit(task.aktiv_seit!)}`}
              onClick={() => onTaskClick(task)}
            >
              {task.titel}
            </button>
          );
        })}
        {jetztMin >= viewStart && jetztMin <= viewEnde && (
          <div className="jetzt" style={{ left: `${((jetztMin - viewStart) / spanne) * 100}%` }} />
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
        <span className="leiste-nav">
          <button type="button" className="sekundaer" aria-label="Stunde zurück"
                  onClick={() => setOffset(klemmen(offset - 60))}>
            ‹
          </button>
          <button type="button" className="sekundaer" aria-label="Stunde vor"
                  onClick={() => setOffset(klemmen(offset + 60))}>
            ›
          </button>
          {klemmen(offset) !== 0 && (
            <button type="button" className="sekundaer" onClick={() => setOffset(0)}>
              Auto
            </button>
          )}
        </span>
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
