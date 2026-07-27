import type {
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

export const api = {
  // Die Queue eines Tages, Default heute.
  tasks: (datum?: string) => request<Task[]>(`/tasks${datum ? `?datum=${datum}` : ""}`),
  tasksErledigt: () => request<Task[]>("/tasks?erledigt=true"),
  // Zeitpunkt (lokal, ISO) datiert das Erledigen fürs Nachtragen zurück.
  erledigen: (id: number, zeitpunkt?: string) =>
    request<Task>(`/tasks/${id}/erledigt`, {
      method: "POST",
      body: JSON.stringify(zeitpunkt ? { zeitpunkt } : {}),
    }),
  wiederOeffnen: (id: number) => request<Task>(`/tasks/${id}/erledigt`, { method: "DELETE" }),
  taskAnlegen: (titel: string, geplant_am?: string) =>
    request<Task>("/tasks", { method: "POST", body: JSON.stringify({ titel, geplant_am }) }),
  taskAendern: (
    id: number,
    daten: { titel?: string; beschreibung?: string; dauer_minuten?: number; geplant_am?: string },
  ) => request<Task>(`/tasks/${id}`, { method: "PATCH", body: JSON.stringify(daten) }),
  // Automatischer Statuswechsel: Rollover fahren, ggf. den nächsten Queue-Task
  // aktivieren und die heutige Task-Liste zurückgeben.
  queueTick: () => request<Task[]>("/queue/tick", { method: "POST" }),
  // Feierabend: alle aktiven Tasks wandern auf next, der Tick bleibt danach still.
  feierabend: () => request<Task[]>("/queue/feierabend", { method: "POST" }),
  taskLoeschen: (id: number) => request<void>(`/tasks/${id}`, { method: "DELETE" }),
  historie: (id: number) => request<TagEvent[]>(`/tasks/${id}/historie`),
  tagSetzen: (id: number, tag: Tag) => request<Task>(`/tasks/${id}/tags/${tag}`, { method: "PUT" }),
  tagEntfernen: (id: number, tag: Tag) =>
    request<Task>(`/tasks/${id}/tags/${tag}`, { method: "DELETE" }),
  umsortieren: (taskIds: number[], datum?: string) =>
    request<Task[]>("/queue/order", {
      method: "PUT",
      body: JSON.stringify({ task_ids: taskIds, datum }),
    }),
  kapazitaet: (datum?: string) =>
    request<Capacity>(`/capacity${datum ? `?datum=${datum}` : ""}`),
  // Alle Phasen, die den Tag überlappen (auch von verschobenen/archivierten Tasks).
  phasen: (datum?: string) => request<Phase[]>(`/phasen${datum ? `?datum=${datum}` : ""}`),
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
  schedule: () => request<Schedule>("/schedule"),
  scheduleSetzen: (daten: Schedule) =>
    request<Schedule>("/schedule", { method: "PUT", body: JSON.stringify(daten) }),
  // Wochen-Export als JSON-Objekt, der Download passiert im Aufrufer.
  exportWoche: (woche: string) => request<unknown>(`/export?woche=${woche}`),
};
