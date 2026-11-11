"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getTemplates } from "../lib/api";
import type { Template } from "../lib/types";
import { SiteNav } from "./components/site-nav";

const categories: Array<{ kind: Template["kind"]; title: string; subtitle: string; copy: string }> = [
  { kind: "sticker", title: "表情包", subtitle: "Sticker studio", copy: "把今天的情绪，变成一张可以马上发出去的图。" },
  { kind: "wallpaper", title: "手机壁纸", subtitle: "Wallpaper studio", copy: "为你的锁屏留一张只属于你的画面。" },
];

export default function HomePage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  useEffect(() => { getTemplates().then((payload) => setTemplates(payload.items)).catch(() => setTemplates([])); }, []);

  return (
    <main className="gallery-page">
      <SiteNav active="all" />
      <section className="landing-hero">
        <p className="landing-kicker">PERSONAL VISUAL STUDIO</p>
        <h1>一张照片，<span>一张作品。</span></h1>
        <p>选择一个创作空间，再挑一张你喜欢的参考模板。图个乐负责把灵感变成可以保存、分享的图片。</p>
        <div className="landing-search" aria-label="选择创作空间"><div><span>从哪里开始</span><strong>选择一个创作空间</strong></div><div><span>当前模板</span><strong>{templates.length ? `${templates.length} 个模板可用` : "正在读取模板"}</strong></div><Link href="/category/sticker" aria-label="开始创作">→</Link></div>
      </section>

      <section className="category-section" aria-labelledby="category-title">
        <div className="section-heading"><div><h2 id="category-title">选择你的创作空间 <span>→</span></h2><p>每个空间都有自己的模板和输出比例。</p></div></div>
        <div className="category-grid">
          {categories.map((category) => {
            const template = templates.find((item) => item.kind === category.kind);
            return <Link className="category-card" href={`/category/${category.kind}`} key={category.kind}>
              <div className="category-image">{template?.reference_image_url ? <img src={template.reference_image_url} alt={`${category.title}参考图`} /> : <div className="image-skeleton" />}</div>
              <div className="category-card-copy"><div><small>{category.subtitle}</small><h3>{category.title}</h3><p>{category.copy}</p></div><span className="category-arrow">↗</span></div>
            </Link>;
          })}
        </div>
      </section>

      <footer className="site-footer"><div><strong>图个乐</strong><span>让灵感先有一张图</span></div><div><span>照片只用于本次生成</span><span>V1 · 本地验收</span></div></footer>
    </main>
  );
}
