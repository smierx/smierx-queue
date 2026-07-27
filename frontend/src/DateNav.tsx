export function heuteIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

function verschieben(datum: string, tage: number): string {
  const d = new Date(`${datum}T12:00:00`); // Mittag, damit DST nichts verschiebt
  d.setDate(d.getDate() + tage);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

export function datumLabel(datum: string): string {
  if (datum === heuteIso()) return "Heute";
  if (datum === verschieben(heuteIso(), 1)) return "Morgen";
  if (datum === verschieben(heuteIso(), -1)) return "Gestern";
  return new Date(`${datum}T12:00:00`).toLocaleDateString("de-DE", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
  });
}

export function DateNav({ datum, onChange }: { datum: string; onChange: (d: string) => void }) {
  return (
    <span className="date-nav">
      <button
        type="button"
        className="sekundaer"
        aria-label="Tag zurück"
        onClick={() => onChange(verschieben(datum, -1))}
      >
        ‹
      </button>
      <input type="date" value={datum} onChange={(e) => e.target.value && onChange(e.target.value)} />
      <button
        type="button"
        className="sekundaer"
        aria-label="Tag vor"
        onClick={() => onChange(verschieben(datum, 1))}
      >
        ›
      </button>
      {datum !== heuteIso() && (
        <button type="button" className="sekundaer" onClick={() => onChange(heuteIso())}>
          Heute
        </button>
      )}
    </span>
  );
}
