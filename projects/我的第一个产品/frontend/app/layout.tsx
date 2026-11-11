import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "图个乐 · 专属视觉实验室",
  description: "上传一张照片，选择一个模板，生成你的专属贴纸或壁纸。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
