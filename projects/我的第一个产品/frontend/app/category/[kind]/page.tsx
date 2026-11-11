"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { createTask, downloadAsset, getTemplates, uploadImage } from "../../../lib/api";
import { aspectOptionsFor, findAspectRatio } from "../../../lib/aspect-ratios";
import type { Task, Template } from "../../../lib/types";
import { templateSize, validateUpload } from "../../../lib/ui";
import { SiteNav } from "../../components/site-nav";

const OWNER_DEFAULT = "demo-owner";

export default function CategoryPage() {
  const params = useParams<{ kind: string }>();
  const kind = params.kind === "wallpaper" ? "wallpaper" : "sticker";
  const isWallpaper = kind === "wallpaper";
  const title = isWallpaper ? "手机壁纸" : "表情包";
  const subtitle = isWallpaper ? "为锁屏挑一张只属于你的画面" : "把今天的情绪，变成一张可以发出去的图";
  const [templates, setTemplates] = useState<Template[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [aspectRatio, setAspectRatio] = useState(isWallpaper ? "9:19.5" : "1:1");
  const [owner, setOwner] = useState(OWNER_DEFAULT);
  const [file, setFile] = useState<File>();
  const [previewUrl, setPreviewUrl] = useState<string>();
  const [resultUrl, setResultUrl] = useState<string>();
  const [task, setTask] = useState<Task>();
  const [step, setStep] = useState<"ready" | "uploading" | "generating" | "done">("ready");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);
  const selectedTemplate = templates.find((item) => item.template_id === templateId);
  const ratioOptions = aspectOptionsFor(selectedTemplate);
  const selectedRatio = findAspectRatio(aspectRatio, selectedTemplate) || ratioOptions[0];

  useEffect(() => {
    let active = true;
    getTemplates().then((payload) => {
      if (!active) return;
      const items = payload.items.filter((item) => item.kind === kind);
      setTemplates(items);
      const first = items[0];
      setTemplateId(first?.template_id ?? "");
      if (first?.default_aspect_ratio) setAspectRatio(first.default_aspect_ratio);
    }).catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : "模板加载失败。"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [kind]);

  useEffect(() => {
    if (!file) {
      // Object URLs are browser state mirrored into React for the preview.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPreviewUrl(undefined);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function chooseTemplate(template: Template) { setTemplateId(template.template_id); setAspectRatio(template.default_aspect_ratio || (isWallpaper ? "9:19.5" : "1:1")); }
  function onFileChange(event: ChangeEvent<HTMLInputElement>) { const next = event.target.files?.[0]; const message = validateUpload(next); setError(message ?? ""); if (!message) setFile(next); }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const uploadError = validateUpload(file);
    if (uploadError) { setError(uploadError); return; }
    if (!selectedTemplate) { setError("先选择一个参考模板。"); return; }
    const normalizedOwner = owner.trim() || OWNER_DEFAULT;
    setOwner(normalizedOwner); setError(""); setTask(undefined); setResultUrl(undefined);
    try {
      setStep("uploading");
      const upload = await uploadImage(file as File, normalizedOwner);
      setStep("generating");
      const nextTask = await createTask(selectedTemplate.template_id, upload.upload_id, normalizedOwner, aspectRatio);
      setTask(nextTask);
      if (nextTask.versions[0]?.asset_url) setResultUrl(await downloadAsset(nextTask.versions[0].asset_url, normalizedOwner));
      setStep("done");
    } catch (reason: unknown) { setStep("ready"); setError(reason instanceof Error ? reason.message : "生成失败，请稍后再试。"); }
  }

  const stepLabel = step === "uploading" ? "正在上传" : step === "generating" ? "正在生成" : step === "done" ? "已完成" : "等待开始";

  return <main className="gallery-page">
    <SiteNav active={kind} />
    <div className="category-shell">
      <div className="breadcrumbs"><Link href="/">首页</Link><span>/</span><strong>{title}</strong></div>
      <section className="category-hero"><div><p className="landing-kicker">{isWallpaper ? "WALLPAPER STUDIO" : "STICKER STUDIO"}</p><h1>{title} <span>模板</span></h1><p>{subtitle}。选择一张参考图，再决定最终输出比例。</p></div><div className="category-count">{templates.length || "—"}<small>个参考模板</small></div></section>

      <section className="template-section-page" aria-labelledby="template-title"><div className="section-heading"><div><h2 id="template-title">挑选参考模板 <span>→</span></h2><p>图片是风格参考，生成时会结合你上传的照片。</p></div><div className="carousel-controls"><button type="button" aria-label="上一页">‹</button><button type="button" aria-label="下一页">›</button></div></div>
        <div className="template-gallery-grid">{loading ? <div className="loading-card">正在读取模板…</div> : templates.map((template) => <button className={`listing-card ${template.template_id === templateId ? "selected" : ""}`} key={template.template_id} type="button" onClick={() => chooseTemplate(template)} aria-pressed={template.template_id === templateId}><div className="listing-image"><img src={template.reference_image_url || "/template-references/wallpaper-sunrise.png"} alt={`${template.name}参考图`} /><span className="favorite-badge">参考模板</span><span className="heart-button" aria-hidden="true">{template.template_id === templateId ? "♥" : "♡"}</span></div><strong>{template.name}</strong><span>{templateSize(template)} · {template.template_id === templateId ? "已选择" : "点击选择"}</span></button>)}</div>
      </section>

      <section className="creation-section"><form className="search-capsule creation-form" onSubmit={onSubmit}><div className="search-field"><span>参考模板</span><strong>{selectedTemplate?.name || "选择一个模板"}</strong></div><div className="search-field"><label htmlFor="ratio">输出比例</label><select id="ratio" value={aspectRatio} onChange={(event) => setAspectRatio(event.target.value)} disabled={step !== "ready" || !selectedTemplate}>{ratioOptions.map((option) => <option key={option.value} value={option.value}>{option.label} · {option.note}</option>)}</select></div><div className="search-field upload-field"><label htmlFor="photo">上传照片</label><input ref={inputRef} id="photo" type="file" accept="image/jpeg,image/png,image/webp" onChange={onFileChange} disabled={step !== "ready"} /><strong>{file ? file.name : "选择 JPG / PNG / WebP"}</strong></div><button className="search-submit" type="submit" disabled={step !== "ready" || loading || !selectedTemplate}>→</button></form><div className="creation-meta"><span>当前输出尺寸：<strong>{selectedRatio ? `${selectedRatio.width} × ${selectedRatio.height}` : "—"}</strong></span><span>用户标识：<input value={owner} onChange={(event) => setOwner(event.target.value)} aria-label="测试用户标识" /></span><span className="creation-status">{stepLabel}</span></div>{error && <p className="error" role="alert">{error}</p>}</section>

      <section className="result-section"><div className="section-heading"><div><h2>你的作品 <span>→</span></h2><p>{resultUrl ? "这张图片已经准备好下载。" : "生成结果会出现在这里。"}</p></div></div><div className="result-layout"><div className="result-frame">{resultUrl ? <img src={resultUrl} alt="生成结果" /> : previewUrl ? <img src={previewUrl} alt="待生成的照片预览" /> : <div className="result-empty"><span>✦</span><strong>还没有作品</strong><small>选择模板、上传照片后开始生成</small></div>}</div><aside className="result-info"><div><span>任务状态</span><strong>{stepLabel}</strong></div><div><span>生成通道</span><strong>{task?.provider || "SenseNova"}</strong></div><div><span>输出比例</span><strong>{selectedRatio?.label || "—"}</strong></div><div><span>耗时</span><strong>{task?.elapsed_ms ? `${(task.elapsed_ms / 1000).toFixed(1)} 秒` : "—"}</strong></div>{resultUrl && <a className="inverse-button" href={resultUrl} download="tuglele-result.png">下载作品</a>}<div className="review-note">审核后台窗口已预留<br /><small>V1 暂不启用内容审核</small></div></aside></div></section>
    </div>
    <footer className="site-footer"><div><strong>图个乐</strong><span>让灵感先有一张图</span></div><div><span>照片只用于本次生成</span><span>V1 · 本地验收</span></div></footer>
  </main>;
}
