export type Template = {
  template_id: string;
  name: string;
  kind: "sticker" | "wallpaper";
  target_width: number;
  target_height: number;
  prompt_key: string;
  reference_image_url?: string | null;
  default_aspect_ratio?: string | null;
};

export type Version = {
  version_id: string;
  version_no: number;
  status: string;
  provider: string;
  asset_url: string | null;
};

export type Task = {
  task_id: string;
  owner_id: string;
  template_id: string;
  status: string;
  provider: string;
  version_id: string | null;
  versions: Version[];
  elapsed_ms: number | null;
  cost_cents: number | null;
  aspect_ratio?: string | null;
  output_width?: number | null;
  output_height?: number | null;
};

export type ApiErrorShape = { error?: { code?: string; message?: string } };
