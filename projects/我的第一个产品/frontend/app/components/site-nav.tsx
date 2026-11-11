import Link from "next/link";

export function SiteNav({ active }: { active?: "all" | "sticker" | "wallpaper" }) {
  return (
    <header className="site-nav">
      <Link className="site-brand" href="/" aria-label="图个乐首页"><span className="site-brand-mark">图</span><strong>图个乐</strong></Link>
      <nav className="site-tabs" aria-label="主导航">
        <Link className={active === "all" ? "active" : ""} href="/"><span>⌂</span><small>全部</small></Link>
        <Link className={active === "sticker" ? "active" : ""} href="/category/sticker"><span>☺</span><small>表情包</small></Link>
        <Link className={active === "wallpaper" ? "active" : ""} href="/category/wallpaper"><span>▧</span><small>手机壁纸</small></Link>
      </nav>
      <div className="site-actions"><span className="host-link">模板后台</span><button type="button" aria-label="语言">◎</button><button type="button" aria-label="菜单">☰</button></div>
    </header>
  );
}
