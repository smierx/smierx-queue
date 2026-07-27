import type {
  Bereich,
  Capacity,
  Phase,
  Schedule,
  Tag,
  TagEvent,
  Task,
  TimeBlock,
} from "./types";

async function request<T>(pfad: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };

  const antwort = await fetch(`/api${pfad}`, { headers, ...init });
  if (!antwort.ok) {
    const detail = await antwort.text();
    throw new Error(`${antwort.status}: ${detail}`);
  }
  return antwort.status === 204 ? (undefined as T) : antwort.json();
}

function query(params: Record<string, string | undefined>): string {
  const q = new URLSearchParams();
  for (const [key, wert] of Object.entries(params)) {
    if (wert !== undefined) q.set(key, wert);
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const api = {
  // Die Queue eines Tages und Bereichs, Default heute/arbeit.
  tasks: (bereich: Bereich, datum?: string) =>
    request<Task[]>(`/tasks${query({ bereich, datum })}`),
  tasksErledigt: (bereich: Bereich) =>
    request<Task[]>(`/tasks${query({ bereich, erledigt: "true" })}`),
  // Zeitpunkt (lokal, ISO) datiert das Erledigen fürs Nachtragen zurück.
  erledigen: (id: number, zeitpunkt?: string) =>
    request<Task>(`/tasks/${id}/erledigt`, {
      method: "POST",
      body: JSON.stringify(zeitpunkt ? { zeitpunkt } : {}),
    }),
  wiederOeffnen: (id: number) => request<Task>(`/tasks/${id}/erledigt`, { method: "DELETE" }),
  taskAnlegen: (titel: string, bereich: Bereich, geplant_am?: string) =>
    request<Task>("/tasks", {
      method: "POST",
      body: JSON.stringify({ titel, bereich, geplant_am }),
    }),
  taskAendern: (
    id: number,
    daten: {
      titel?: string;
      beschreibung?: string;
      dauer_minuten?: number;
      geplant_am?: string;
      bereich?: Bereich;
    },
  ) => request<Task>(`/tasks/${id}`, { method: "PATCH", body: JSON.stringify(daten) }),
  // Automatischer Statuswechsel: Rollover fahren, Übergabe beider Bereiche prüfen
  // und die heutige Liste des angefragten Bereichs zurückgeben.
  queueTick: (bereich: Bereich) =>
    request<Task[]>(`/queue/tick${query({ bereich })}`, { method: "POST" }),
  // Feierabend im Bereich: aktive Tasks auf next, der Tick bleibt danach still.
  feierabend: (bereich: Bereich) =>
    request<Task[]>(`/queue/feierabend${query({ bereich })}`, { method: "POST" }),
  taskLoeschen: (id: number) => request<void>(`/tasks/${id}`, { method: "DELETE" }),
  historie: (id: number) => request<TagEvent[]>(`/tasks/${id}/historie`),
  tagSetzen: (id: number, tag: Tag) => request<Task>(`/tasks/${id}/tags/${tag}`, { method: "PUT" }),
  tagEntfernen: (id: number, tag: Tag) =>
    request<Task>(`/tasks/${id}/tags/${tag}`, { method: "DELETE" }),
  umsortieren: (taskIds: number[], bereich: Bereich, datum?: string) =>
    request<Task[]>("/queue/order", {
      method: "PUT",
      body: JSON.stringify({ task_ids: taskIds, bereich, datum }),
    }),
  kapazitaet: (bereich: Bereich, datum?: string) =>
    request<Capacity>(`/capacity${query({ bereich, datum })}`),
  // Alle Phasen des Bereichs, die den Tag überlappen (auch von verschobenen/
  // archivierten Tasks).
  phasen: (bereich: Bereich, datum?: string) =>
    request<Phase[]>(`/phasen${query({ bereich, datum })}`),
  phaseAnlegen: (taskId: number, daten: { von: string; bis: string }) =>
    request<Phase>(`/tasks/${taskId}/phasen`, { method: "POST", body: JSON.stringify(daten) }),
  phaseAendern: (id: number, daten: { von?: string; bis?: string }) =>
    request<Phase>(`/phasen/${id}`, { method: "PATCH", body: JSON.stringify(daten) }),
  phaseLoeschen: (id: number) => request<void>(`/phasen/${id}`, { method: "DELETE" }),
  timeblockAnlegen: (daten: Omit<TimeBlock, "id">) =>
    request<TimeBlock>("/timeblocks", { method: "POST", body: JSON.stringify(daten) }),
  timeblockAendern: (id: number, daten: Omit<TimeBlock, "id">) =>
    request<TimeBlock>(`/timeblocks/${id}`, { method: "PUT", body: JSON.stringify(daten) }),
  timeblockLoeschen: (id: number) => request<void>(`/timeblocks/${id}`, { method: "DELETE" }),
  schedule: (bereich: Bereich) => request<Schedule>(`/schedule${query({ bereich })}`),
  scheduleSetzen: (daten: Schedule, bereich: Bereich) =>
    request<Schedule>(`/schedule${query({ bereich })}`, {
      method: "PUT",
      body: JSON.stringify(daten),
    }),
  // Wochen-Export als JSON-Objekt, der Download passiert im Aufrufer.
  exportWoche: (woche: string, bereich: Bereich) =>
    request<unknown>(`/export${query({ woche, bereich })}`),
};
