export const ALLE_TAGS = [
  "aktiv",
  "next",
  "critical",
  "support",
  "discussion",
  "holding",
  "pausiert",
  "inaktiv",
] as const;

export type Tag = (typeof ALLE_TAGS)[number];

export interface Task {
  id: number;
  titel: string;
  beschreibung: string;
  position: number;
  tags: Tag[];
  erstellt_am: string;
  geaendert_am: string;
  erledigt_am: string | null;
  aktiv_seit: string | null;
}

export interface Schedule {
  modus: "stunden" | "feste_zeiten";
  stunden_pro_tag: number;
  zeiten: Record<string, [string, string] | null> | null;
}

export interface TagEvent {
  tag: Tag;
  aktion: "gesetzt" | "entfernt";
  zeitpunkt: string;
}

export interface TimeBlock {
  id: number;
  titel: string;
  typ: "meeting" | "blocker";
  start: string;
  ende: string;
}

export interface GitlabConnection {
  url: string;
  projekt_ids: number[];
}

export interface SyncResult {
  importiert: number;
  aktualisiert_lokal: number;
  gepusht: number;
  geschlossen: number;
  wieder_geoeffnet: number;
  konflikte: string[];
}

export interface SyncLogEintrag {
  zeitpunkt: string;
  aktion: "sync" | "issue_close" | "issue_reopen";
  details: Record<string, unknown>;
}

export interface Capacity {
  datum: string;
  modus: "stunden" | "feste_zeiten";
  arbeitszeit_minuten: number;
  geblockt_minuten: number;
  frei_minuten: number;
  fenster_von: string | null;
  fenster_bis: string | null;
  bloecke: TimeBlock[];
}
