"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import SettingsModal from "@/components/SettingsModal";
import "./globals.css";

const NAV = [
  { href: "/",        icon: "▤",  label: "Videos",   desc: "Video library" },
  { href: "/upload",  icon: "↑",  label: "Upload",   desc: "Import documents" },
  { href: "/search",  icon: "⌕",  label: "Search",   desc: "Find & ask" },
  { href: "/queue",   icon: "✎",  label: "Work Queue", desc: "Needs your edit" },
  { href: "/stats",   icon: "◈",  label: "Progress", desc: "Dataset quality" },
  { href: "/glossary",icon: "⬡",  label: "Glossary", desc: "Theological terms" },
  { href: "/export",  icon: "↓",  label: "Export",   desc: "Download dataset" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const pathname  = usePathname();
  const [settings, setSettings] = useState(false);

  return (
    <html lang="en">
      <head>
        <title>OMI-TED v2</title>
        <meta name="description" content="Telugu Christian theology translation engine" />
      </head>
      <body style={{ background: "var(--gray-50)", minHeight: "100vh", display: "flex" }}>

        {/* ── Left Sidebar ── */}
        <aside style={{
          width: 200, flexShrink: 0, minHeight: "100vh",
          background: "var(--white)", borderRight: "1px solid var(--gray-200)",
          display: "flex", flexDirection: "column", position: "sticky", top: 0, height: "100vh",
        }}>
          {/* Logo */}
          <Link href="/" style={{ display: "flex", alignItems: "center", gap: 10, padding: "20px 20px 16px", textDecoration: "none", borderBottom: "1px solid var(--gray-100)" }}>
            <div style={{ width: 32, height: 32, background: "var(--rose)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <span style={{ color: "#fff", fontSize: 12, fontWeight: 800 }}>OM</span>
            </div>
            <div>
              <p style={{ fontSize: 13, fontWeight: 700, color: "var(--gray-900)", lineHeight: 1.2 }}>OMI-TED</p>
              <p style={{ fontSize: 9, color: "var(--gray-400)", fontFamily: "JetBrains Mono", letterSpacing: "0.06em" }}>te → en · theology</p>
            </div>
          </Link>

          {/* Nav items */}
          <nav style={{ flex: 1, padding: "12px 10px", display: "flex", flexDirection: "column", gap: 2 }}>
            {NAV.map(({ href, icon, label, desc }) => {
              const active = pathname === href || (href !== "/" && pathname.startsWith(href));
              return (
                <Link key={href} href={href} style={{
                  display: "flex", alignItems: "center", gap: 10, padding: "9px 10px",
                  borderRadius: 8, textDecoration: "none", transition: "background 0.12s",
                  background: active ? "var(--rose-light)" : "transparent",
                }}>
                  <span style={{ fontSize: 15, width: 20, textAlign: "center", color: active ? "var(--rose)" : "var(--gray-400)" }}>
                    {icon}
                  </span>
                  <div>
                    <p style={{ fontSize: 13, fontWeight: active ? 600 : 400, color: active ? "var(--rose)" : "var(--gray-700, #374151)", lineHeight: 1.2 }}>
                      {label}
                    </p>
                  </div>
                </Link>
              );
            })}
          </nav>

          {/* Settings at bottom */}
          <div style={{ padding: "12px 10px", borderTop: "1px solid var(--gray-100)" }}>
            <motion.button onClick={() => setSettings(true)}
              whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }}
              style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, padding: "9px 10px", borderRadius: 8, border: "none", background: "transparent", cursor: "pointer", textAlign: "left" }}>
              <span style={{ fontSize: 15, width: 20, textAlign: "center", color: "var(--gray-400)" }}>⚙</span>
              <span style={{ fontSize: 13, color: "var(--gray-500)" }}>Settings</span>
            </motion.button>
          </div>
        </aside>

        {/* ── Main content ── */}
        <main style={{ flex: 1, minWidth: 0 }}>
          <motion.div
            key={pathname}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            style={{ padding: "28px 32px", maxWidth: 1200 }}>
            {children}
          </motion.div>
        </main>

        <SettingsModal open={settings} onClose={() => setSettings(false)} />
      </body>
    </html>
  );
}
