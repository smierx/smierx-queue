import { useEffect, useRef, useState } from "react";

import { api } from "./api";
import {
  BLOCK_TYPEN,
  type Bereich,
  type BlockTyp,
  type Capacity,
  type Phase,
  type Task,
  type TimeBlock,
} from "./types";

const BLOCK_NAMEN: Record<BlockTyp, string> = {
  meeting: "Meeting",
  blocker: "Blocker",
  support: "Support",
};

// Vertikales Layout der Achse: Task-Ebenen beginnen unter der Termin-Spur.
const EBENE_TOP = 56;
const EBENE_HOEHE = 34;
const TAG_ENDE = 24 * 60;

export type LeistenModus = "heute" | "vergangen" | "zukunft";

function minuten(iso: string): number {
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes();
}

function alsZeit(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function alsUhr(min: number): string {
  const voll = Math.min(Math.max(Math.round(min), 0), TAG_ENDE - 1);
  return `${String(Math.floor(voll / 60)).padStart(2, "0")}:${String(voll % 60).padStart(2, "0")}`;
}

function dauerText(minuten: number): string {
  const h = Math.floor(minuten / 60);
  const m = minuten % 60;
  if (h === 0) return `${m} min`;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
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
  typ: BlockTyp;
  von: string;
  bis: string;
}

// Zeitabschnitt in Minuten seit Mitternacht des angezeigten Tages.
interface Seg {
  von: number;
  bis: number;
}

// Ein Balken im Zeitstrahl: eine Phase, von Blocker-Fenstern in Segmente zerteilt.
interface Balken {
  phase: Phase;
  task: Task | null; // null, wenn der Task nicht (mehr) auf diesem Tag liegt
  segs: Seg[];
  art: "laeuft" | "vergangen";
  ueberzogen: boolean;
  ende: number; // effektives Ende (fürs Anstellen der Warteliste)
  basisEnde: number; // Ende mit gespeicherter Dauer (fürs Auto-Fenster, zappelt nicht beim Ziehen)
  ebene: number;
  key: string;
}

export function Tagesleiste({
  datum,
  bereich,
  modus,
  kapazitaet,
  phasen,
  aktive,
  geplante,
  onChange,
  onTaskClick,
  onPhaseClick,
  onPhaseNeu,
}: {
  datum: string; // YYYY-MM-DD, der angezeigte Tag
  bereich: Bereich;
  modus: LeistenModus;
  kapazitaet: Capacity;
  phasen: Phase[];
  aktive: Task[];
  geplante: Task[];
  onChange: () => void;
  onTaskClick: (task: Task) => void;
  onPhaseClick?: (phase: Phase) => void; // Vergangenheits-Editor, sonst Task-Detail
  onPhaseNeu?: () => void; // "+ Phase" an vergangenen Tagen
}) {
  const [form, setForm] = useState<FormDaten | null>(null);
  const [sende, setSende] = useState(false);
  // Verschiebung der Achse in Minuten relativ zum Auto-Fenster.
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    if (!form) return;
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") setForm(null);
    }
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [form]);
  const drag = useRef<{ x: number; offset: number; bewegt: boolean } | null>(null);
  const achseRef = useRef<HTMLDivElement>(null);

  // Ziehen am rechten Balkenrand ändert die Dauer. Während des Ziehens hält
  // resizeDauer den Live-Wert, gespeichert wird erst beim Loslassen.
  const resize = useRef<{
    id: number;
    x: number;
    dauer0: number;
    dauer: number;
    minProPx: number;
    bewegt: boolean;
  } | null>(null);
  const [resizeDauer, setResizeDauer] = useState<{ id: number; dauer: number } | null>(null);
  const klickSperre = useRef(false);

  // Nach dem Speichern kommt die neue Dauer über die Props zurück, dann darf
  // der Live-Wert weg. Nicht mitten im Ziehen (Poll alle 30s).
  useEffect(() => {
    if (!resize.current) setResizeDauer(null);
  }, [aktive, geplante, phasen]);

  const effektiveDauer = (t: Task) =>
    resizeDauer?.id === t.id ? resizeDauer.dauer : t.dauer_minuten;

  const jetzt = new Date();
  const jetztMin = jetzt.getHours() * 60 + jetzt.getMinutes();
  const tagStart = new Date(`${datum}T00:00:00`);
  const minAbTag = (d: Date) => (d.getTime() - tagStart.getTime()) / 60_000;
  const tagesTasks = [...aktive, ...geplante];

  function amTagUm(zeit: string): string {
    return `${datum}T${zeit}:00`;
  }

  // Blocker und Meetings als sortierte, überlappungsfreie Fenster. Sie zählen
  // nicht als Arbeitszeit und zerteilen alle Task-Balken.
  const fenster: Seg[] = [];
  for (const block of [...kapazitaet.bloecke].sort((a, b) => minuten(a.start) - minuten(b.start))) {
    const von = Math.max(0, minuten(block.start));
    const bis = Math.min(TAG_ENDE, minuten(block.ende));
    if (bis <= von) continue;
    const letztes = fenster[fenster.length - 1];
    if (letztes && von <= letztes.bis) letztes.bis = Math.max(letztes.bis, bis);
    else fenster.push({ von, bis });
  }

  // Dauer ab einem Startpunkt in freie Segmente legen. Blocker-Fenster werden
  // übersprungen und schieben das Ende nach hinten.
  function freieSegmente(von: number, dauer: number): { segs: Seg[]; ende: number } {
    const segs: Seg[] = [];
    let cursor = von;
    let rest = dauer;
    for (const f of fenster) {
      if (f.bis <= cursor) continue;
      const frei = f.von - cursor;
      if (frei >= rest) break;
      if (frei > 0) {
        segs.push({ von: cursor, bis: f.von });
        rest -= frei;
      }
      cursor = Math.max(cursor, f.bis);
    }
    segs.push({ von: cursor, bis: cursor + rest });
    return { segs, ende: cursor + rest };
  }

  // Festen Zeitraum nur optisch an den Fenstern auftrennen (vergangene Phasen,
  // da wird keine Zeit nachgeschoben).
  function zerschneide(von: number, bis: number): Seg[] {
    const segs: Seg[] = [];
    let cursor = von;
    for (const f of fenster) {
      if (f.bis <= cursor) continue;
      if (f.von >= bis) break;
      if (f.von > cursor) segs.push({ von: cursor, bis: f.von });
      cursor = f.bis;
      if (cursor >= bis) break;
    }
    if (cursor < bis) segs.push({ von: cursor, bis });
    return segs;
  }

  // Die Balken kommen aus den Phasen des Tages (GET /phasen). Phasen über
  // Mitternacht werden auf den Tag geclippt.
  const balken: Balken[] = [];
  for (const phase of phasen) {
    const task = tagesTasks.find((t) => t.id === phase.task_id) ?? null;
    const vonMin = Math.max(0, minAbTag(new Date(phase.von)));
    if (vonMin >= TAG_ENDE) continue;
    if (phase.bis === null) {
      // Läuft noch: nur heute möglich. Balken über die geplante Dauer; ist die
      // Schätzung überzogen, wächst er einfach mit der Realität weiter
      // (Dauer ist kein Wecker, gewechselt wird von Hand).
      if (modus !== "heute") continue;
      const dauer = task ? effektiveDauer(task) : 60;
      const { segs, ende } = freieSegmente(vonMin, dauer);
      const ueberzogen = ende <= jetztMin;
      const echteSegs = ueberzogen ? zerschneide(vonMin, Math.max(jetztMin, vonMin + 2)) : segs;
      const echtesEnde = ueberzogen ? jetztMin : ende;
      const basisEnde =
        task && resizeDauer?.id === task.id
          ? freieSegmente(vonMin, task.dauer_minuten).ende
          : echtesEnde;
      balken.push({
        phase, task, segs: echteSegs, art: "laeuft", ueberzogen,
        ende: echtesEnde, basisEnde, ebene: 0, key: `p${phase.id}`,
      });
    } else {
      const bisMin = Math.min(TAG_ENDE, minAbTag(new Date(phase.bis)));
      if (bisMin <= 0) continue; // Phase liegt vor dem Tag
      const segs = zerschneide(vonMin, Math.max(bisMin, vonMin + 2));
      if (segs.length === 0) continue; // lag komplett in einem Blocker
      balken.push({
        phase, task, segs, art: "vergangen", ueberzogen: false,
        ende: bisMin, basisEnde: bisMin, ebene: 0, key: `p${phase.id}`,
      });
    }
  }
  // Ebenen-Zuordnung: überlappende Balken rutschen eine Ebene tiefer.
  balken.sort(
    (a, b) => a.segs[0].von - b.segs[0].von || a.segs[a.segs.length - 1].bis - b.segs[b.segs.length - 1].bis,
  );
  const ebenenEnden: number[] = [];
  for (const b of balken) {
    let ebene = ebenenEnden.findIndex((ende) => ende <= b.segs[0].von);
    if (ebene < 0) {
      ebene = ebenenEnden.length;
      ebenenEnden.push(0);
    }
    b.ebene = ebene;
    ebenenEnden[ebene] = b.segs[b.segs.length - 1].bis;
  }

  // Arbeitsfenster-Beginn (für die Warteliste an Zukunftstagen).
  let fensterStart = 7 * 60;
  if (kapazitaet.fenster_von) {
    const [h, m] = kapazitaet.fenster_von.split(":").map(Number);
    fensterStart = h * 60 + m;
  }

  // Warteliste: alle Queue-Tasks nacheinander in genau einer Ebene. Heute hinter
  // jetzt, den laufenden Tasks und allen Blockern; an Zukunftstagen ab dem
  // Arbeitsfenster-Beginn. Vergangene Tage haben keine Warteliste.
  const geplant: { task: Task; segs: Seg[] }[] = [];
  if (modus !== "vergangen") {
    let cursor =
      modus === "heute"
        ? Math.max(jetztMin, ...balken.filter((b) => b.art === "laeuft").map((b) => b.ende))
        : fensterStart;
    for (const t of geplante) {
      if (cursor >= TAG_ENDE) break; // Rest liegt hinter Mitternacht, unsichtbar
      const { segs, ende } = freieSegmente(cursor, effektiveDauer(t));
      geplant.push({ task: t, segs });
      cursor = ende;
    }
  }
  const geplantEbene = ebenenEnden.length;
  const achseHoehe = Math.max(
    92,
    EBENE_TOP + (ebenenEnden.length + (geplant.length ? 1 : 0)) * EBENE_HOEHE + 2,
  );

  // Auto-Fenster: feste Zeiten aus dem Arbeitszeit-Modell, im Stunden-Modus 07 bis 16 Uhr.
  // Blöcke und Task-Balken außerhalb weiten das Fenster, damit nichts unsichtbar bleibt.
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
  for (const b of balken) {
    if (b.segs[0].von > 0) autoStart = Math.min(autoStart, b.segs[0].von);
    autoEnde = Math.max(autoEnde, Math.min(b.basisEnde, TAG_ENDE));
  }
  if (modus === "heute") autoEnde = Math.max(autoEnde, jetztMin);
  for (const g of geplant) {
    autoEnde = Math.max(autoEnde, Math.min(g.segs[g.segs.length - 1].bis, TAG_ENDE));
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

  function resizeStart(e: React.PointerEvent<HTMLSpanElement>, task: Task) {
    e.stopPropagation(); // sonst startet das Achsen-Verschieben
    e.preventDefault();
    const breite = achseRef.current?.clientWidth || 1;
    resize.current = {
      id: task.id,
      x: e.clientX,
      dauer0: task.dauer_minuten,
      dauer: task.dauer_minuten,
      minProPx: spanne / breite,
      bewegt: false,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
    setResizeDauer({ id: task.id, dauer: task.dauer_minuten });
  }

  function resizeMove(e: React.PointerEvent<HTMLSpanElement>) {
    const r = resize.current;
    if (!r) return;
    const roh = r.dauer0 + (e.clientX - r.x) * r.minProPx;
    const neu = Math.min(Math.max(Math.round(roh / 5) * 5, 15), 24 * 60);
    if (neu !== r.dauer) {
      r.dauer = neu;
      r.bewegt = true;
      setResizeDauer({ id: r.id, dauer: neu });
    }
  }

  async function resizeEnde() {
    const r = resize.current;
    resize.current = null;
    if (!r) return;
    if (r.bewegt) {
      // Der Klick direkt nach dem Loslassen soll nicht das Modal öffnen.
      klickSperre.current = true;
      setTimeout(() => (klickSperre.current = false), 0);
    }
    if (r.dauer !== r.dauer0) {
      await api.taskAendern(r.id, { dauer_minuten: r.dauer });
      onChange(); // resizeDauer räumt der useEffect auf, sobald die Props nachziehen
    } else {
      setResizeDauer(null);
    }
  }

  function resizeGriff(task: Task) {
    return (
      <span
        className="resize-griff"
        title="Ziehen um die Dauer zu ändern"
        onPointerDown={(e) => resizeStart(e, task)}
        onPointerMove={resizeMove}
        onPointerUp={resizeEnde}
        onPointerCancel={resizeEnde}
      />
    );
  }

  function balkenKlick(b: Balken) {
    if (klickSperre.current) return;
    if (modus === "vergangen" && onPhaseClick) onPhaseClick(b.phase);
    else if (b.task) onTaskClick(b.task);
    else if (onPhaseClick) onPhaseClick(b.phase); // Task liegt woanders, Phase editieren
  }

  async function spontanBlocker() {
    // Ein Klick: Blocker ab jetzt für 30 Minuten. Details danach anpassbar.
    const von = jetztZeit();
    const block = await api.timeblockAnlegen({
      titel: "Unterbrechung",
      typ: "blocker",
      bereich,
      start: amTagUm(von),
      ende: amTagUm(zeitPlus(von, 30)),
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
    if (!form || !form.titel.trim() || sende) return;
    setSende(true);
    try {
      const daten = {
        titel: form.titel.trim(),
        typ: form.typ,
        bereich,
        start: amTagUm(form.von),
        ende: amTagUm(form.bis),
      };
      if (form.id === null) await api.timeblockAnlegen(daten);
      else await api.timeblockAendern(form.id, daten);
      setForm(null);
      onChange();
    } finally {
      setSende(false);
    }
  }

  async function loeschen() {
    if (form?.id != null) {
      await api.timeblockLoeschen(form.id);
      setForm(null);
      onChange();
    }
  }

  return (
    <div className={`tagesleiste ${modus}`}>
      <div
        ref={achseRef}
        className="achse"
        style={{ height: achseHoehe }}
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
        {balken.map((b) =>
          b.segs.map((seg, i) => {
            const pos = position(seg.von, Math.min(seg.bis, TAG_ENDE));
            if (!pos) return null;
            const info =
              b.art === "laeuft"
                ? `läuft seit ${alsUhr(b.segs[0].von)}, geplant ${dauerText(
                    b.task ? effektiveDauer(b.task) : 60,
                  )}`
                : `war aktiv ${alsUhr(b.segs[0].von)}–${alsUhr(b.ende)}`;
            return (
              <button
                key={`${b.key}-${i}`}
                type="button"
                className={`block task ${b.art === "vergangen" ? "vergangen" : ""} ${
                  b.ueberzogen ? "ueberzogen" : ""
                }`}
                style={{ ...pos, top: EBENE_TOP + b.ebene * EBENE_HOEHE }}
                title={`${b.phase.titel} – ${info}`}
                onClick={() => balkenKlick(b)}
              >
                {b.phase.titel}
                {b.art === "laeuft" && b.task && i === b.segs.length - 1 && resizeGriff(b.task)}
              </button>
            );
          }),
        )}
        {geplant.map(({ task, segs }) =>
          segs.map((seg, i) => {
            const pos = position(seg.von, Math.min(seg.bis, TAG_ENDE));
            if (!pos) return null;
            return (
              <button
                key={`g${task.id}-${i}`}
                type="button"
                className="block task geplant"
                style={{ ...pos, top: EBENE_TOP + geplantEbene * EBENE_HOEHE }}
                title={`${task.titel} – geplant ab ${alsUhr(segs[0].von)}, ${dauerText(effektiveDauer(task))}`}
                onClick={() => !klickSperre.current && onTaskClick(task)}
              >
                {task.titel}
                {i === segs.length - 1 && resizeGriff(task)}
              </button>
            );
          }),
        )}
        {modus === "heute" && jetztMin >= viewStart && jetztMin <= viewEnde && (
          <div className="jetzt" style={{ left: `${((jetztMin - viewStart) / spanne) * 100}%` }} />
        )}
      </div>
      <div className="leiste-fuss">
        {modus === "heute" && (
          <button type="button" className="spontan" onClick={spontanBlocker}>
            ⚡ Blocker jetzt
          </button>
        )}
        {modus === "vergangen" && onPhaseNeu && (
          <button type="button" className="sekundaer" onClick={onPhaseNeu}>
            + Phase
          </button>
        )}
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
        <div className="modal-hintergrund" onClick={() => setForm(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <form onSubmit={speichern}>
              <label>
                Titel
                <input
                  value={form.titel}
                  onChange={(e) => setForm({ ...form, titel: e.target.value })}
                  placeholder="Titel"
                />
              </label>
              <label>
                Typ
                <select
                  value={form.typ}
                  onChange={(e) => setForm({ ...form, typ: e.target.value as BlockTyp })}
                >
                  {BLOCK_TYPEN.map((typ) => (
                    <option key={typ} value={typ}>
                      {BLOCK_NAMEN[typ]}
                    </option>
                  ))}
                </select>
              </label>
              <div className="zeit-zeile">
                <label>
                  Von
                  <input
                    type="time"
                    value={form.von}
                    onChange={(e) => setForm({ ...form, von: e.target.value })}
                  />
                </label>
                <label>
                  Bis
                  <input
                    type="time"
                    value={form.bis}
                    onChange={(e) => setForm({ ...form, bis: e.target.value })}
                  />
                </label>
                {form.id !== null && modus === "heute" && (
                  <button
                    type="button"
                    className="sekundaer"
                    title="Endzeit auf jetzt setzen"
                    onClick={() => setForm({ ...form, bis: jetztZeit() })}
                  >
                    Bis jetzt
                  </button>
                )}
              </div>
              <div className="modal-aktionen">
                {form.id !== null && (
                  <button type="button" className="sekundaer" onClick={loeschen}>
                    Löschen
                  </button>
                )}
                <button type="button" className="sekundaer" onClick={() => setForm(null)}>
                  Abbrechen
                </button>
                <button type="submit" disabled={sende}>
                  {form.id === null ? "Eintragen" : "Speichern"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
