"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import SettingsModal from "@/components/SettingsModal";
import "./globals.css";

const NAV = [
  { href: "/",         icon: "▤", label: "Videos",     labelTe: "వీడియోలు",  desc: "Video library",     descTe: "వీడియో లైబ్రరీ" },
  { href: "/dashboard",icon: "▦", label: "Ingest",     labelTe: "సేకరణ",      desc: "Bulk dashboard",    descTe: "బల్క్ డాష్‌బోర్డ్" },
  { href: "/translate",icon: "⇄", label: "Translate",  labelTe: "అనువదించు",  desc: "Translation control",descTe: "అనువాద నియంత్రణ" },
  { href: "/errors",   icon: "⚠", label: "Errors",     labelTe: "లోపాలు",     desc: "Ingest & translation",descTe: "సేకరణ & అనువాదం" },
  { href: "/removed",  icon: "🗑", label: "Recycle Bin", labelTe: "రీసైకిల్ బిన్", desc: "Removed videos", descTe: "తొలగించిన వీడియోలు" },
  { href: "/upload",   icon: "↑", label: "Upload",     labelTe: "అప్‌లోడ్",   desc: "Import documents",  descTe: "పత్రాలను దిగుమతి చేయండి" },
  { href: "/search",   icon: "⌕", label: "Search",     labelTe: "శోధన",       desc: "Find & ask",        descTe: "కనుగొని అడగండి" },
  { href: "/queue",    icon: "✎", label: "Work Queue", labelTe: "పని వరుస",   desc: "Needs your edit",   descTe: "మీ సవరణ అవసరం" },
  { href: "/stats",    icon: "◈", label: "Progress",   labelTe: "పురోగతి",    desc: "Dataset quality",   descTe: "డేటాసెట్ నాణ్యత" },
  { href: "/glossary", icon: "⬡", label: "Glossary",   labelTe: "పదకోశం",     desc: "Theological terms", descTe: "వేదాంత పదాలు" },
  { href: "/export",   icon: "↓", label: "Export",     labelTe: "ఎగుమతి",     desc: "Download dataset",  descTe: "డేటాసెట్‌ను డౌన్‌లోడ్ చేయండి" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const pathname  = usePathname();
  const [settings, setSettings] = useState(false);
  const [drawer, setDrawer]     = useState(false);
  const [lang, setLang]         = useState<"en" | "te">("en");

  // Load saved language after mount (avoids SSR/hydration mismatch).
  useEffect(() => {
    const saved = localStorage.getItem("omited.lang");
    if (saved === "te" || saved === "en") setLang(saved);
  }, []);
  const changeLang = (l: "en" | "te") => {
    setLang(l);
    try { localStorage.setItem("omited.lang", l); } catch { /* private mode */ }
  };
  const te = lang === "te";

  const closeDrawer = () => setDrawer(false);

  return (
    <html lang="en">
      <head>
        <title>OMI-TED v2</title>
        <meta name="description" content="Telugu Christian theology translation engine" />
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
      </head>
      <body style={{ background: "var(--gray-50)", minHeight: "100vh" }}>
        <div className="app-shell">

          {/* ── Mobile backdrop ── */}
          <div className={`app-backdrop${drawer ? " open" : ""}`} onClick={closeDrawer} />

          {/* ── Sidebar (drawer on mobile) ── */}
          <aside className={`app-sidebar${drawer ? " open" : ""}`}>
            <Link href="/" onClick={closeDrawer} style={{ display: "flex", alignItems: "center", gap: 10, padding: "20px 20px 16px", textDecoration: "none", borderBottom: "1px solid var(--gray-100)" }}>
              <div style={{ width: 32, height: 32, background: "var(--rose)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <span style={{ color: "#fff", fontSize: 12, fontWeight: 800 }}>OM</span>
              </div>
              <div>
                <p style={{ fontSize: 13, fontWeight: 700, color: "var(--gray-900)", lineHeight: 1.2 }}>OMI-TED</p>
                <p style={{ fontSize: 9, color: "var(--gray-400)", fontFamily: "JetBrains Mono", letterSpacing: "0.06em" }}>te → en · theology</p>
              </div>
            </Link>

            <nav style={{ flex: 1, padding: "12px 10px", display: "flex", flexDirection: "column", gap: 2, overflowY: "auto" }}>
              {NAV.map(({ href, icon, label, labelTe, desc, descTe }) => {
                const active = pathname === href || (href !== "/" && pathname.startsWith(href));
                return (
                  <Link key={href} href={href} onClick={closeDrawer} style={{
                    display: "flex", alignItems: "center", gap: 10, padding: "8px 10px",
                    borderRadius: 8, textDecoration: "none", transition: "background 0.12s",
                    background: active ? "var(--rose-light)" : "transparent",
                  }}>
                    <span style={{ fontSize: 15, width: 20, textAlign: "center", flexShrink: 0, color: active ? "var(--rose)" : "var(--gray-400)" }}>{icon}</span>
                    <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                      <span style={{ fontSize: 13, fontWeight: active ? 600 : 400, color: active ? "var(--rose)" : "var(--gray-700, #374151)", lineHeight: 1.25 }}>{te ? labelTe : label}</span>
                      <span style={{ fontSize: 10.5, color: active ? "var(--rose)" : "var(--gray-400)", opacity: 0.9, lineHeight: 1.3, marginTop: 1 }}>{te ? descTe : desc}</span>
                    </span>
                  </Link>
                );
              })}
            </nav>

            <div style={{ padding: "12px 10px", borderTop: "1px solid var(--gray-100)" }}>
              {/* Language toggle — English / Telugu (menu labels + sub-items) */}
              <div style={{ display: "flex", gap: 4, padding: 4, marginBottom: 8, background: "var(--gray-100)", borderRadius: 9 }}>
                {(["en", "te"] as const).map((l) => (
                  <button key={l} onClick={() => changeLang(l)}
                    title={l === "en" ? "English" : "తెలుగు"} aria-pressed={lang === l}
                    style={{
                      flex: 1, padding: "5px 0", borderRadius: 6, border: "none", cursor: "pointer",
                      fontSize: 11, fontWeight: 600, transition: "background 0.12s, color 0.12s",
                      background: lang === l ? "var(--white)" : "transparent",
                      color: lang === l ? "var(--rose)" : "var(--gray-500)",
                      boxShadow: lang === l ? "0 1px 2px rgba(0,0,0,0.10)" : "none",
                    }}>
                    {l === "en" ? "EN" : "తె"}
                  </button>
                ))}
              </div>

              <motion.button onClick={() => { setSettings(true); closeDrawer(); }}
                whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }}
                style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, padding: "9px 10px", borderRadius: 8, border: "none", background: "transparent", cursor: "pointer", textAlign: "left" }}>
                <span style={{ fontSize: 15, width: 20, textAlign: "center", color: "var(--gray-400)" }}>⚙</span>
                <span style={{ fontSize: 13, color: "var(--gray-500)" }}>{te ? "సెట్టింగ్‌లు" : "Settings"}</span>
              </motion.button>
            </div>
          </aside>

          {/* ── Main column ── */}
          <main className="app-main">
            {/* Mobile top bar with hamburger (hidden on desktop via CSS) */}
            <div className="app-topbar">
              <button aria-label="Menu" onClick={() => setDrawer(true)}
                style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 20, lineHeight: 1, color: "var(--gray-700,#374151)", padding: 4 }}>≡</button>
              <Link href="/" style={{ display: "flex", alignItems: "center", gap: 8, textDecoration: "none" }}>
                <div style={{ width: 26, height: 26, background: "var(--rose)", borderRadius: 7, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <span style={{ color: "#fff", fontSize: 10, fontWeight: 800 }}>OM</span>
                </div>
                <span style={{ fontSize: 13, fontWeight: 700, color: "var(--gray-900)" }}>OMI-TED</span>
              </Link>
            </div>

            <motion.div
              key={pathname}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className="app-main-inner">
              {children}
            </motion.div>
          </main>
        </div>

        <SettingsModal open={settings} onClose={() => setSettings(false)} />
      </body>
    </html>
  );
}
