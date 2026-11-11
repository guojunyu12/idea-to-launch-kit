import { describe, expect, it } from "vitest";
import { errorMessage, validateUpload } from "../lib/ui";

describe("test workbench UI rules", () => {
  it("normalizes backend error envelopes", () => {
    expect(errorMessage({ error: { message: "任务不存在" } }, 404)).toBe("任务不存在");
    expect(errorMessage({}, 502)).toBe("请求失败（502）");
  });

  it("rejects unsupported and oversized uploads", () => {
    expect(validateUpload(new File(["x"], "a.txt", { type: "text/plain" }))).toContain("只支持");
    expect(validateUpload(new File([new Uint8Array(11 * 1024 * 1024)], "a.png", { type: "image/png" }))).toContain("10MB");
    expect(validateUpload(undefined)).toContain("选择");
  });
});
