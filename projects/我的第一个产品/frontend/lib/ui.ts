import type { ApiErrorShape, Template } from "./types";

export function errorMessage(payload: ApiErrorShape, status: number): string {
  return payload.error?.message || `请求失败（${status}）`;
}

export function templateSize(template: Template): string {
  return `${template.target_width} × ${template.target_height}`;
}

export function validateUpload(file: File | undefined): string | null {
  if (!file) return "先选择一张图片。";
  const allowed = ["image/jpeg", "image/png", "image/webp"];
  if (!allowed.includes(file.type)) return "只支持 JPG、PNG 或 WebP 图片。";
  if (file.size > 10 * 1024 * 1024) return "图片不能超过 10MB。";
  return null;
}
