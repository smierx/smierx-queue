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
}

export interface TimeBlock {
  id: number;
  titel: string;
  typ: "meeting" | "blocker";
  start: string;
  ende: string;
}

export interface Capacity {
  datum: string;
  modus: "stunden" | "feste_zeiten";
  arbeitszeit_minuten: number;
  geblockt_minuten: number;
  frei_minuten: number;
  bloecke: TimeBlock[];
}
