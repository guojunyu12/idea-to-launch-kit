import type { Task, Template } from "./types";
import { errorMessage } from "./ui";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(errorMessage(payload, response.status));
  return payload as T;
}

export function getTemplates(): Promise<{ items: Template[] }> {
  return request("/api/v1/templates");
}

export function uploadImage(file: File, owner: string): Promise<{ upload_id: string }> {
  const body = new FormData();
  body.append("file", file);
  return request("/api/v1/uploads", { method: "POST", headers: { "X-Owner-ID": owner }, body });
}

export function createTask(templateId: string, uploadId: string, owner: string, aspectRatio?: string): Promise<Task> {
  return request("/api/v1/tasks", {
    method: "POST",
    headers: { "X-Owner-ID": owner, "Content-Type": "application/json" },
    body: JSON.stringify({ template_id: templateId, upload_id: uploadId, ...(aspectRatio ? { aspect_ratio: aspectRatio } : {}) })
  });
}

export async function downloadAsset(assetUrl: string, owner: string): Promise<string> {
  const response = await fetch(`${API_BASE}${assetUrl}`, { headers: { "X-Owner-ID": owner } });
  if (!response.ok) throw new Error("生成完成，但结果下载失败。");
  return URL.createObjectURL(await response.blob());
}
