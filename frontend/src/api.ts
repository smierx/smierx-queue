import type { Capacity, Tag, Task } from "./types";

async function request<T>(pfad: string, init?: RequestInit): Promise<T> {
  const antwort = await fetch(`/api${pfad}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!antwort.ok) {
    const detail = await antwort.text();
    throw new Error(`${antwort.status}: ${detail}`);
  }
  return antwort.status === 204 ? (undefined as T) : antwort.json();
}

export const api = {
  tasks: () => request<Task[]>("/tasks"),
  taskAnlegen: (titel: string) =>
    request<Task>("/tasks", { method: "POST", body: JSON.stringify({ titel }) }),
  taskLoeschen: (id: number) => request<void>(`/tasks/${id}`, { method: "DELETE" }),
  tagSetzen: (id: number, tag: Tag) => request<Task>(`/tasks/${id}/tags/${tag}`, { method: "PUT" }),
  tagEntfernen: (id: number, tag: Tag) =>
    request<Task>(`/tasks/${id}/tags/${tag}`, { method: "DELETE" }),
  umsortieren: (taskIds: number[]) =>
    request<Task[]>("/queue/order", { method: "PUT", body: JSON.stringify({ task_ids: taskIds }) }),
  kapazitaet: () => request<Capacity>("/capacity"),
};
