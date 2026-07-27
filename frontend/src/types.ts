export const ALLE_TAGS = [
  "aktiv",
  "next",
  "critical",
  "discussion",
  "holding",
  "pausiert",
  "inaktiv",
] as const;

// Support ist bewusst ein Blocker-Typ und kein Task-Tag: Support-Zeit blockt den Tag.
export const BLOCK_TYPEN = ["meeting", "blocker", "support"] as const;

export type BlockTyp = (typeof BLOCK_TYPEN)[number];

export type Tag = (typeof ALLE_TAGS)[number];

export interface Task {
  id: number;
  titel: string;
  beschreibung: string;
  position: number;
  dauer_minuten: number;
  tags: Tag[];
  erstellt_am: string;
  geaendert_am: string;
  erledigt_am: string | null;
  aktiv_seit: string | null;
  aktiv_phasen: { von: string; bis: string | null }[];
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
  typ: BlockTyp;
  start: string;
  ende: string;
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
