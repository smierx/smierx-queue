import { useEffect, useState } from "react";

import { api } from "./api";
import type { SyncLogEintrag, SyncResult } from "./types";

function logZeile(eintrag: SyncLogEintrag): string {
  const zeit = new Date(eintrag.zeitpunkt).toLocaleString("de-DE");
  const d = eintrag.details;
  if (eintrag.aktion === "sync") {
    return `${zeit} – Sync: ${d.importiert} importiert, ${d.aktualisiert_lokal} aktualisiert, ${d.gepusht} gepusht, ${d.geschlossen} erledigt, ${d.wieder_geoeffnet} wieder geöffnet`;
  }
  const was = eintrag.aktion === "issue_close" ? "Issue geschlossen" : "Issue wieder geöffnet";
  const status = d.ok ? "" : ` – FEHLER: ${d.fehler}`;
  return `${zeit} – ${was}: ${d.projekt_id}#${d.issue_iid}${status}`;
}

export function GitLabPanel({ onSynced }: { onSynced: () => void }) {
  const [offen, setOffen] = useState(false);
  const [verbunden, setVerbunden] = useState(false);
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [projekte, setProjekte] = useState("");
  const [ergebnis, setErgebnis] = useState<SyncResult | null>(null);
  const [log, setLog] = useState<SyncLogEintrag[]>([]);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    if (offen && verbunden) api.gitlabLog().then(setLog).catch(() => {});
  }, [offen, verbunden, ergebnis]);

  useEffect(() => {
    api
      .gitlabConnection()
      .then((c) => {
        setVerbunden(true);
        setUrl(c.url);
        setProjekte(c.projekt_ids.join(", "));
      })
      .catch(() => setVerbunden(false));
  }, []);

  async function speichern(event: React.FormEvent) {
    event.preventDefault();
    setFehler(null);
    try {
      const projekt_ids = projekte
        .split(",")
        .map((s) => parseInt(s.trim(), 10))
        .filter((n) => !isNaN(n));
      await api.gitlabVerbinden({ url, token, projekt_ids });
      setVerbunden(true);
      setToken("");
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    }
  }

  async function sync() {
    setFehler(null);
    try {
      const r = await api.gitlabSync();
      setErgebnis(r);
      onSynced();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section>
      <h2>
        <button type="button" className="aufklappen" onClick={() => setOffen(!offen)}>
          GitLab-Sync {verbunden ? "(verbunden)" : "(optional)"} {offen ? "▾" : "▸"}
        </button>
      </h2>
      {offen && (
        <div className="gitlab-panel">
          <form onSubmit={speichern}>
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://gitlab.example.com"
            />
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder={verbunden ? "Token (leer = behalten)" : "Personal Access Token"}
            />
            <input
              value={projekte}
              onChange={(e) => setProjekte(e.target.value)}
              placeholder="Projekt-Ids, z.B. 42, 87"
            />
            <button type="submit">Speichern</button>
            {verbunden && (
              <button type="button" className="sekundaer" onClick={sync}>
                Jetzt syncen
              </button>
            )}
          </form>
          {fehler && <p className="fehler">{fehler}</p>}
          {ergebnis && ergebnis.konflikte.length > 0 && (
            <p className="sync-ergebnis">
              {ergebnis.konflikte.map((k) => (
                <small key={k}>
                  Konflikt: {k}
                  <br />
                </small>
              ))}
            </p>
          )}
          {log.length > 0 && (
            <ul className="sync-log">
              {log.map((eintrag, i) => (
                <li key={i}>{logZeile(eintrag)}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
