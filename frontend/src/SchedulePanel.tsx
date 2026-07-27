import { useEffect, useState } from "react";

import { api } from "./api";
import type { Bereich, Schedule } from "./types";

const WOCHENTAGE: [string, string][] = [
  ["mo", "Mo"],
  ["di", "Di"],
  ["mi", "Mi"],
  ["do", "Do"],
  ["fr", "Fr"],
  ["sa", "Sa"],
  ["so", "So"],
];

const DEFAULT_FENSTER: [string, string] = ["08:00", "16:30"];

export function SchedulePanel({ bereich, onChange }: {
  bereich: Bereich;
  onChange: () => void;
}) {
  const [offen, setOffen] = useState(false);
  const [schedule, setSchedule] = useState<Schedule | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    setSchedule(null); // altes Modell nicht anzeigen, während der Wechsel lädt
    api.schedule(bereich).then(setSchedule).catch(() => {});
  }, [bereich]);

  if (!schedule) return null;

  async function speichern(event: React.FormEvent) {
    event.preventDefault();
    if (!schedule) return;
    setFehler(null);
    try {
      const zeiten =
        schedule.modus === "feste_zeiten"
          ? Object.fromEntries(WOCHENTAGE.map(([key]) => [key, schedule.zeiten?.[key] ?? null]))
          : schedule.zeiten;
      setSchedule(await api.scheduleSetzen({ ...schedule, zeiten }, bereich));
      onChange();
      setOffen(false);
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    }
  }

  function tagSetzen(key: string, fenster: [string, string] | null) {
    if (!schedule) return;
    setSchedule({ ...schedule, zeiten: { ...(schedule.zeiten ?? {}), [key]: fenster } });
  }

  return (
    <section>
      <h2>
        <button type="button" className="aufklappen" onClick={() => setOffen(!offen)}>
          Arbeitszeit (
          {schedule.modus === "stunden"
            ? `${schedule.stunden_pro_tag} h pro Tag`
            : "feste Zeiten"}
          ) {offen ? "▾" : "▸"}
        </button>
      </h2>
      {offen && (
        <form onSubmit={speichern} className="schedule-panel">
          <div className="modus-wahl">
            <label>
              <input
                type="radio"
                checked={schedule.modus === "stunden"}
                onChange={() => setSchedule({ ...schedule, modus: "stunden" })}
              />
              Stunden pro Tag
            </label>
            <label>
              <input
                type="radio"
                checked={schedule.modus === "feste_zeiten"}
                onChange={() => setSchedule({ ...schedule, modus: "feste_zeiten" })}
              />
              Feste Zeiten
            </label>
          </div>

          {schedule.modus === "stunden" ? (
            <label className="stunden-feld">
              Stunden
              <input
                type="number"
                min={0.5}
                max={24}
                step={0.5}
                value={schedule.stunden_pro_tag}
                onChange={(e) =>
                  setSchedule({ ...schedule, stunden_pro_tag: Number(e.target.value) })
                }
              />
            </label>
          ) : (
            <div className="tage">
              {WOCHENTAGE.map(([key, name]) => {
                const fenster = schedule.zeiten?.[key] ?? null;
                return (
                  <div key={key} className="tag-zeile">
                    <label className="tag-name">
                      <input
                        type="checkbox"
                        checked={fenster !== null}
                        onChange={(e) =>
                          tagSetzen(key, e.target.checked ? DEFAULT_FENSTER : null)
                        }
                      />
                      {name}
                    </label>
                    {fenster && (
                      <>
                        <input
                          type="time"
                          value={fenster[0]}
                          onChange={(e) => tagSetzen(key, [e.target.value, fenster[1]])}
                        />
                        <span>bis</span>
                        <input
                          type="time"
                          value={fenster[1]}
                          onChange={(e) => tagSetzen(key, [fenster[0], e.target.value])}
                        />
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {fehler && <p className="fehler">{fehler}</p>}
          <button type="submit">Speichern</button>
        </form>
      )}
    </section>
  );
}
