"use client";
import useSWR from "swr";
import Link from "next/link";
import axios from "axios";
import { motion } from "motion/react";

interface TermTranslation { translation: string; count: number; }
interface TopTerm { word: string; occurrences: number; translations: TermTranslation[]; consistent: boolean; }
interface DatasetStats {
  total_segments: number; gold_segments: number; silver_segments: number; empty_segments: number;
  est_tokens_gold: number; est_tokens_silver: number; gold_pct: number; silver_pct: number;
  top_terms: TopTerm[];
}

const fetcher = (u: string) => axios.get(u).then(r => r.data);

const stagger = { hidden: {}, show: { transition: { staggerChildren: 0.06 } } };
const fadeUp  = { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 380, damping: 28 } } };

export default function ProgressPage() {
  const { data, error, isLoading } = useSWR<DatasetStats>("/api/v1/stats", fetcher, { refreshInterval: 8000 });

  const inconsistent = data?.top_terms.filter(t => !t.consistent) ?? [];
  const consistent   = data?.top_terms.filter(t =>  t.consistent) ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <div>
        <h1 style={{ fontSize: 20, fontWeight: 600, color: "var(--gray-900)" }}>Progress</h1>
        <p style={{ fontSize: 13, color: "var(--gray-400)", marginTop: 4 }}>
          How much of your dataset is human-quality vs auto-translated.
        </p>
      </div>

      {isLoading && <p style={{ color: "var(--gray-400)", fontSize: 13, padding: "40px 0", textAlign: "center" }}>Loading…</p>}
      {error    && <p style={{ color: "var(--red)",      fontSize: 13, padding: "40px 0", textAlign: "center" }}>Backend not reachable.</p>}

      {data && (
        <>
          {/* Quality tier cards */}
          <motion.div variants={stagger} initial="hidden" animate="show"
            className="grid-auto" style={{ gap: 16 }}>
            {[
              { label: "Your edits",       n: data.gold_segments,   pct: data.gold_pct,   color: "var(--rose)",  bg: "var(--rose-light)",  border: "var(--rose-border)",  desc: "Human-verified · gold quality" },
              { label: "Auto-translated",  n: data.silver_segments, pct: data.silver_pct, color: "var(--amber)", bg: "var(--amber-light)", border: "var(--amber-border)", desc: "Machine only · review before using" },
              { label: "Not translated",   n: data.empty_segments,  pct: 100-data.gold_pct-data.silver_pct, color: "var(--gray-400)", bg: "var(--gray-100)", border: "var(--gray-200)", desc: "No translation yet · unusable" },
            ].map(({ label, n, pct, color, bg, border, desc }) => (
              <motion.div key={label} variants={fadeUp}
                style={{ background: "var(--white)", border: "1px solid var(--gray-200)", borderRadius: 12, padding: "20px 20px 16px" }}>
                <p style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--gray-400)", marginBottom: 10 }}>{label}</p>
                <p style={{ fontSize: 32, fontWeight: 700, color, lineHeight: 1 }}>{n.toLocaleString()}</p>
                <p style={{ fontSize: 12, color: "var(--gray-400)", marginTop: 4, marginBottom: 14 }}>{desc}</p>
                <div style={{ height: 4, borderRadius: 99, background: "var(--gray-100)", overflow: "hidden" }}>
                  <motion.div style={{ height: "100%", borderRadius: 99, background: color }}
                    initial={{ width: 0 }} animate={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                    transition={{ duration: 0.8, ease: [0.22,1,0.36,1] }} />
                </div>
                <p style={{ fontSize: 11, color, marginTop: 6, fontFamily: "JetBrains Mono" }}>{Math.max(0,pct).toFixed(1)}%</p>
              </motion.div>
            ))}
          </motion.div>

          {/* Overall bar */}
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
            style={{ background: "var(--white)", border: "1px solid var(--gray-200)", borderRadius: 12, padding: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
              <p style={{ fontSize: 13, fontWeight: 600, color: "var(--gray-900)" }}>
                {data.total_segments.toLocaleString()} segments total
              </p>
              <p style={{ fontSize: 12, color: "var(--gray-400)" }}>
                {data.gold_segments.toLocaleString()} human-edited
              </p>
            </div>
            <div style={{ height: 10, borderRadius: 99, background: "var(--gray-100)", overflow: "hidden", display: "flex", gap: 1 }}>
              {[
                { pct: data.gold_pct,                                    color: "var(--rose)" },
                { pct: data.silver_pct,                                  color: "var(--amber)" },
                { pct: Math.max(0, 100-data.gold_pct-data.silver_pct),  color: "var(--gray-200)" },
              ].map(({ pct, color }, i) => (
                <motion.div key={i} style={{ background: color, height: "100%" }}
                  initial={{ width: 0 }} animate={{ width: `${Math.max(0,pct)}%` }}
                  transition={{ duration: 0.9, delay: i * 0.08, ease: [0.22,1,0.36,1] }} />
              ))}
            </div>
            <div style={{ display: "flex", gap: 20, marginTop: 10 }}>
              {[{ label: "Gold (human)", color: "var(--rose)" }, { label: "Silver (auto)", color: "var(--amber)" }, { label: "Empty", color: "var(--gray-300)" }].map(({ label, color }) => (
                <span key={label} style={{ fontSize: 11, color: "var(--gray-400)", display: "flex", alignItems: "center", gap: 5 }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }} />
                  {label}
                </span>
              ))}
            </div>
          </motion.div>

          {/* Term consistency */}
          {data.top_terms.length > 0 && (
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
                <h2 style={{ fontSize: 15, fontWeight: 600, color: "var(--gray-900)" }}>Term consistency</h2>
                {inconsistent.length > 0 && (
                  <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 20, background: "#FEF2F2", color: "var(--red)", border: "1px solid #FECACA" }}>
                    {inconsistent.length} inconsistent
                  </span>
                )}
              </div>
              <p style={{ fontSize: 12, color: "var(--gray-400)", marginBottom: 16, lineHeight: 1.6 }}>
                Most frequent Telugu words in your human edits. Same word translated differently across segments is flagged.
                Multiple meanings can be intentional — check and confirm in the editor.
              </p>
              <div className="scroll-x" style={{ background: "var(--white)", border: "1px solid var(--gray-200)", borderRadius: 12 }}>
                <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 520 }}>
                  <thead>
                    <tr style={{ background: "var(--gray-50)", borderBottom: "1px solid var(--gray-200)" }}>
                      {["Word", "In segments", "Your translations", ""].map(h => (
                        <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, fontWeight: 600, color: "var(--gray-400)", textTransform: "uppercase", letterSpacing: "0.06em" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[...inconsistent, ...consistent].map(term => (
                      <tr key={term.word} style={{ borderTop: "1px solid var(--gray-100)", background: !term.consistent ? "#FFFBF5" : "var(--white)" }}>
                        <td style={{ padding: "12px 16px" }}>
                          <span style={{ fontSize: 14, fontFamily: "'Noto Sans Telugu', sans-serif", color: "var(--gray-900)", fontWeight: 500 }}>
                            {term.word}
                          </span>
                        </td>
                        <td style={{ padding: "12px 16px" }}>
                          <span style={{ fontSize: 12, fontFamily: "JetBrains Mono", color: "var(--gray-500)" }}>
                            {term.occurrences}
                          </span>
                        </td>
                        <td style={{ padding: "12px 16px" }}>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                            {term.translations.map(t => (
                              <span key={t.translation} style={{
                                fontSize: 11, padding: "2px 8px", borderRadius: 6, fontWeight: 500,
                                background: term.consistent ? "var(--green-light)" : "var(--rose-light)",
                                color: term.consistent ? "var(--green)" : "var(--rose)",
                                border: `1px solid ${term.consistent ? "var(--green-border)" : "var(--rose-border)"}`,
                                maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                              }}>
                                {t.translation.length > 35 ? t.translation.slice(0,33)+"…" : t.translation}
                                {t.count > 1 && <span style={{ opacity: 0.5 }}> ×{t.count}</span>}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td style={{ padding: "12px 16px", textAlign: "right" }}>
                          {term.consistent
                            ? <span style={{ fontSize: 11, color: "var(--green)" }}>✓</span>
                            : <span style={{ fontSize: 11, color: "var(--amber)", fontWeight: 600 }}>⚠ {term.translations.length} meanings</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {data.top_terms.length === 0 && (
            <div style={{ background: "var(--gray-50)", border: "1px solid var(--gray-200)", borderRadius: 12, padding: "40px 24px", textAlign: "center" }}>
              <p style={{ fontSize: 14, fontWeight: 500, color: "var(--gray-900)", marginBottom: 6 }}>No human edits yet</p>
              <p style={{ fontSize: 12, color: "var(--gray-400)", marginBottom: 16 }}>Go to the editor, type your translations, and come back here to track consistency.</p>
              <Link href="/" style={{ display: "inline-block", padding: "8px 20px", borderRadius: 8, background: "var(--rose)", color: "#fff", fontSize: 12, fontWeight: 600, textDecoration: "none" }}>
                Pick a video to edit →
              </Link>
            </div>
          )}
        </>
      )}
    </div>
  );
}
