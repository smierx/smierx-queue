import { useEffect, useState } from "react";

import { api } from "./api";
import type { SyncResult } from "./types";

export function GitLabPanel({ onSynced }: { onSynced: () => void }) {
  const [offen, setOffen] = useState(false);
  const [verbunden, setVerbunden] = useState(false);
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [projekte, setProjekte] = useState("");
  const [ergebnis, setErgebnis] = useState<SyncResult | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

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
          {ergebnis && (
            <p className="sync-ergebnis">
              {ergebnis.importiert} importiert, {ergebnis.aktualisiert_lokal} aktualisiert,{" "}
              {ergebnis.gepusht} gepusht, {ergebnis.geschlossen} erledigt,{" "}
              {ergebnis.wieder_geoeffnet} wieder geöffnet.
              {ergebnis.konflikte.map((k) => (
                <small key={k}>
                  <br />
                  Konflikt: {k}
                </small>
              ))}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
