import type {
  Capacity,
  GitlabConnection,
  Schedule,
  SyncLogEintrag,
  SyncResult,
  Tag,
  TagEvent,
  Task,
  TimeBlock,
} from "./types";

// Wird in main.tsx gesetzt, sobald Keycloak konfiguriert ist.
let tokenHolen: () => Promise<string | null> = async () => null;

export function setTokenHolen(fn: () => Promise<string | null>) {
  tokenHolen = fn;
}

async function request<T>(pfad: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = await tokenHolen();
  if (token) headers.Authorization = `Bearer ${token}`;

  const antwort = await fetch(`/api${pfad}`, { headers, ...init });
  if (!antwort.ok) {
    const detail = await antwort.text();
    throw new Error(`${antwort.status}: ${detail}`);
  }
  return antwort.status === 204 ? (undefined as T) : antwort.json();
}

export const api = {
  tasks: () => request<Task[]>("/tasks"),
  tasksErledigt: () => request<Task[]>("/tasks?erledigt=true"),
  erledigen: (id: number) => request<Task>(`/tasks/${id}/erledigt`, { method: "POST" }),
  wiederOeffnen: (id: number) => request<Task>(`/tasks/${id}/erledigt`, { method: "DELETE" }),
  taskAnlegen: (titel: string) =>
    request<Task>("/tasks", { method: "POST", body: JSON.stringify({ titel }) }),
  taskAendern: (id: number, daten: { titel?: string; beschreibung?: string }) =>
    request<Task>(`/tasks/${id}`, { method: "PATCH", body: JSON.stringify(daten) }),
  taskLoeschen: (id: number) => request<void>(`/tasks/${id}`, { method: "DELETE" }),
  historie: (id: number) => request<TagEvent[]>(`/tasks/${id}/historie`),
  tagSetzen: (id: number, tag: Tag) => request<Task>(`/tasks/${id}/tags/${tag}`, { method: "PUT" }),
  tagEntfernen: (id: number, tag: Tag) =>
    request<Task>(`/tasks/${id}/tags/${tag}`, { method: "DELETE" }),
  umsortieren: (taskIds: number[]) =>
    request<Task[]>("/queue/order", { method: "PUT", body: JSON.stringify({ task_ids: taskIds }) }),
  kapazitaet: () => request<Capacity>("/capacity"),
  timeblockAnlegen: (daten: Omit<TimeBlock, "id">) =>
    request<TimeBlock>("/timeblocks", { method: "POST", body: JSON.stringify(daten) }),
  timeblockAendern: (id: number, daten: Omit<TimeBlock, "id">) =>
    request<TimeBlock>(`/timeblocks/${id}`, { method: "PUT", body: JSON.stringify(daten) }),
  timeblockLoeschen: (id: number) => request<void>(`/timeblocks/${id}`, { method: "DELETE" }),
  schedule: () => request<Schedule>("/schedule"),
  scheduleSetzen: (daten: Schedule) =>
    request<Schedule>("/schedule", { method: "PUT", body: JSON.stringify(daten) }),
  gitlabConnection: () => request<GitlabConnection>("/gitlab/connection"),
  gitlabVerbinden: (daten: GitlabConnection & { token: string }) =>
    request<GitlabConnection>("/gitlab/connection", {
      method: "PUT",
      body: JSON.stringify(daten),
    }),
  gitlabSync: () => request<SyncResult>("/gitlab/sync", { method: "POST" }),
  gitlabLog: () => request<SyncLogEintrag[]>("/gitlab/log?limit=20"),
};
