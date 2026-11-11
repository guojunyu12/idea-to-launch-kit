import type { Template } from "./types";

export type AspectRatioOption = {
  value: string;
  label: string;
  note: string;
  width: number;
  height: number;
};

// 这些比例覆盖主流 AIGC 画布与常见发布场景；9:6 不是常见的图像比例，按语境采用 9:16 竖屏。
export const ASPECT_RATIOS: AspectRatioOption[] = [
  { value: "1:1", label: "1:1", note: "方形 / 贴纸", width: 512, height: 512 },
  { value: "4:3", label: "4:3", note: "标准横图", width: 1600, height: 1200 },
  { value: "3:2", label: "3:2", note: "摄影横图", width: 1536, height: 1024 },
  { value: "16:9", label: "16:9", note: "宽屏 / 横版", width: 1600, height: 900 },
  { value: "3:4", label: "3:4", note: "竖版照片", width: 1200, height: 1600 },
  { value: "2:3", label: "2:3", note: "摄影竖图", width: 1024, height: 1536 },
  { value: "4:5", label: "4:5", note: "社交竖图", width: 1080, height: 1350 },
  { value: "9:16", label: "9:16", note: "手机壁纸 / 故事", width: 1080, height: 1920 },
  { value: "9:19.5", label: "9:19.5", note: "手机原生屏", width: 1179, height: 2556 },
  { value: "9:21", label: "9:21", note: "超长壁纸", width: 1344, height: 3136 },
];

export function aspectOptionsFor(template: Template | undefined): AspectRatioOption[] {
  if (!template) return ASPECT_RATIOS;
  if (template.kind === "sticker") {
    return ASPECT_RATIOS.filter((item) => ["1:1", "4:3", "3:2", "4:5", "3:4", "2:3"].includes(item.value));
  }
  return ASPECT_RATIOS.filter((item) => ["9:16", "9:19.5", "9:21", "1:1", "4:3", "16:9", "3:4"].includes(item.value));
}

export function findAspectRatio(value: string | undefined, template: Template | undefined): AspectRatioOption | undefined {
  return aspectOptionsFor(template).find((item) => item.value === value);
}
