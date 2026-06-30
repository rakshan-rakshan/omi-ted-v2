"use client";
import { useEffect, useState } from "react";
import useSWR from "swr";
import axios from "axios";
import Link from "next/link";

const fetcher = (u: string) => axios.get(u).then((r) => r.data);

// ── Interfaces ────────────────────────────────────────────────────────────────

interface IngestErrorRow {
  youtube_id: string; title: string | null; status: string;
  error_msg: string | null; finished_at: string | null; attempts: number;
}
interface IngestErrorsResp {
  items: IngestErrorRow[]; total: number; page: number; page_size: number; total_pages: number;
  counts: { error: number; no_transcript: number };
}
interface TrErrorRow {
  id: number; youtube_id: string; title: string | null; run_id: string | null;
  provider: string; model: string | null; segment_index: number | null;
  source_text: string | null; error_type: string; error_msg: string;
  cost_usd: number; created_at: string | null;
}
interface TrErrorsResp {
  items: TrErrorRow[]; total: number; page: number; page_size: number; total_pages: number;
  summary: {
    total_errors: number; cost_on_errored_videos: number;
    by_model: Array<{ provider: string; model: string | null; count: number; cost_usd: number }>;
    by_error_type: Array<{ error_type: string; count: number }>;
  };
}

// ── Constants ─────────────────────────────────────────────────────────────────

const INGEST_STATUS: Record<string, { label: string; color: string; bg: string }> = {
  error:         { label: "Error",       color: "var(--red)",   bg: "var(--red-light)" },
  no_transcript: { label: "No captions", color: "var(--amber)", bg: "var(--amber-light)" },
};

const INGEST_FILTERS = ["all", "error", "no_transcript"];

const TR_TYPE_BADGE: Record<string, { color: string; bg: string }> = {
  auth:      { color: "var(--red)",      bg: "var(--red-light)" },
  rate_limit:{ color: "var(--amber)",    bg: "var(--amber-light)" },
  timeout:   { color: "var(--amber)",    bg: "var(--amber-light)" },
  server:    { color: "var(--red)",      bg: "var(--red-light)" },
  network:   { color: "var(--amber)",    bg: "var(--amber-light)" },
  video:     { color: "var(--red)",      bg: "var(--red-light)" },
  exception: { color: "var(--gray-500)", bg: "var(--gray-100)" },
};

function trTypeBadge(t: string): { color: string; bg: string } {
  return TR_TYPE_BADGE[t] ?? { color: "var(--gray-500)", bg: "var(--gray-100)" };
}

function fmtWhen(s: string | null): string {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ErrorsPage() {
  const [tab, setTab] = useState<"ingest" | "translation">("ingest");

  // ── Ingest tab state ─────────────────────────────────────────────────────
  const [inStatus, setInStatus] = useState("all");
  const [inQ, setInQ] = useState("");
  const [inQDeb, setInQDeb] = useState("");
  const [inPage, setInPage] = useState(1);

  // ── Translation tab state ────────────────────────────────────────────────
  const [trType, setTrType] = useState("");
  const [trQ, setTrQ] = useState("");
  const [trQDeb, setTrQDeb] = useState("");
  const [trPage, setTrPage] = useState(1);

  const pageSize = 50;

  // ── Debounced search per tab ─────────────────────────────────────────────
  useEffect(() => {
    const t = setTimeout(() => { setInQDeb(inQ); setInPage(1); }, 350);
    return () => clearTimeout(t);
  }, [inQ]);

  useEffect(() => {
    const t = setTimeout(() => { setTrQDeb(trQ); setTrPage(1); }, 350);
    return () => clearTimeout(t);
  }, [trQ]);

  // ── SWR: ingest errors ───────────────────────────────────────────────────
  const inParams = new URLSearchParams({ page: String(inPage), page_size: String(pageSize) });
  if (inStatus !== "all") inParams.set("status", inStatus);
  if (inQDeb) inParams.set("q", inQDeb);
  const { data: ingest, isLoading: inLoading, mutate: mutateIngest } = useSWR<IngestErrorsResp>(
    `/api/v1/errors/ingest?${inParams.toString()}`, fetcher,
    { refreshInterval: 0, keepPreviousData: true }
  );

  // ── SWR: translation errors ──────────────────────────────────────────────
  const trParams = new URLSearchParams({ page: String(trPage), page_size: String(pageSize) });
  if (trType) trParams.set("error_type", trType);
  if (trQDeb) trParams.set("q", trQDeb);
  const { data: trErr, isLoading: trLoading } = useSWR<TrErrorsResp>(
    `/api/v1/errors/translation?${trParams.toString()}`, fetcher,
    { refreshInterval: 0, keepPreviousData: true }
  );

  // ── Actions ──────────────────────────────────────────────────────────────
  async function retryIngest(id: string) {
    try { await axios.post("/api/v1/ingest/", { youtube_id: id }); } catch {}
    mutateIngest();
  }

  // ── Shared card helper (identical to dashboard) ──────────────────────────
  const card = (label: string, value: number | string, color = "var(--ink)") => (
    <div style={{ flex: "1 1 130px", minWidth: 120, background: "var(--white)", border: "1px solid var(--warm-200)", borderRadius: 12, padding: "14px 16px", boxShadow: "var(--shadow-card)" }}>
      <p style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</p>
      <p style={{ fontSize: 24, fontWeight: 700, color, fontFamily: "JetBrains Mono", marginTop: 4 }}>{typeof value === "number" ? value.toLocaleString() : value}</p>
    </div>
  );

  const inCounts = ingest?.counts ?? { error: 0, no_transcript: 0 };
  const trSummary = trErr?.summary;

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

      {/* Page title */}
      <div>
        <h1 className="font-display" style={{ fontSize: 26, color: "var(--ink)", letterSpacing: "-0.01em" }}>Errors</h1>
        <p style={{ fontSize: 13, color: "var(--ink-3)", marginTop: 4 }}>
          Ingest failures and translation failures, with full detail.
        </p>
      </div>

      {/* Tab switcher (segmented control) */}
      <div style={{ display: "inline-flex", gap: 4, padding: 4, background: "var(--gray-100)", borderRadius: 10, alignSelf: "flex-start" }}>
        {([
          { id: "ingest", label: "Ingest" },
          { id: "translation", label: "Translation" },
        ] as const).map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} aria-pressed={tab === t.id}
            style={{
              padding: "7px 18px", borderRadius: 7, border: "none", cursor: "pointer",
              fontSize: 13, fontWeight: 600, transition: "background 0.12s, color 0.12s",
              background: tab === t.id ? "var(--white)" : "transparent",
              color: tab === t.id ? "var(--rose)" : "var(--gray-500)",
              boxShadow: tab === t.id ? "0 1px 2px rgba(0,0,0,0.10)" : "none",
            }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ════════════════════════════════════════════════════════════════════
          INGEST TAB
          ════════════════════════════════════════════════════════════════════ */}
      {tab === "ingest" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

          {/* Summary cards */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
            {card("Fetch errors", inCounts.error, "var(--red)")}
            {card("No captions", inCounts.no_transcript, "var(--amber)")}
          </div>

          {/* Filter bar */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
            <select value={inStatus} onChange={(e) => { setInStatus(e.target.value); setInPage(1); }}
              style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, color: "var(--ink)" }}>
              {INGEST_FILTERS.map((f) => <option key={f} value={f}>{f === "all" ? "All statuses" : (INGEST_STATUS[f]?.label ?? f)}</option>)}
            </select>
            <input value={inQ} onChange={(e) => setInQ(e.target.value)} placeholder="Search title or video ID…"
              style={{ flex: "1 1 220px", minWidth: 180, padding: "8px 12px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, outline: "none" }} />
            {ingest && <span style={{ fontSize: 12, color: "var(--ink-3)", whiteSpace: "nowrap" }}>{ingest.total.toLocaleString()} results</span>}
          </div>

          {/* Ingest errors table */}
          <div style={{ background: "var(--white)", borderRadius: 12, border: "1px solid var(--warm-200)", boxShadow: "var(--shadow-card)", overflow: "hidden" }}>
            <div className="scroll-x">
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, minWidth: 720 }}>
                <thead>
                  <tr>
                    {["Title", "Video ID", "Status", "Error", "When", ""].map((h) => (
                      <th key={h} style={{ padding: "11px 16px", textAlign: "left", fontSize: 11, fontWeight: 600, color: "var(--ink-3)", letterSpacing: "0.05em", textTransform: "uppercase", background: "var(--cream)", whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {inLoading && !ingest && <tr><td colSpan={6} style={{ padding: "48px 0", textAlign: "center", color: "var(--ink-3)" }}>Loading…</td></tr>}
                  {ingest?.items.map((r: IngestErrorRow, i: number) => {
                    const s = INGEST_STATUS[r.status] ?? { label: r.status, color: "var(--gray-500)", bg: "var(--gray-100)" };
                    return (
                      <tr key={r.youtube_id} style={{ borderTop: i > 0 ? "1px solid var(--warm-100)" : "none" }}>
                        <td style={{ padding: "12px 16px", maxWidth: 320 }}>
                          <p style={{ fontWeight: 500, color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 320 }}>{r.title || "—"}</p>
                          {r.attempts > 0 && <p style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 2, fontFamily: "JetBrains Mono" }}>{r.attempts} attempt{r.attempts === 1 ? "" : "s"}</p>}
                        </td>
                        <td style={{ padding: "12px 16px", fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--ink-3)", whiteSpace: "nowrap" }}>
                          <a href={`https://youtu.be/${r.youtube_id}`} target="_blank" rel="noreferrer" style={{ color: "var(--ink-3)", textDecoration: "none" }}>{r.youtube_id}</a>
                        </td>
                        <td style={{ padding: "12px 16px" }}>
                          <span style={{ fontSize: 11, fontWeight: 600, padding: "3px 9px", borderRadius: 20, background: s.bg, color: s.color, whiteSpace: "nowrap" }}>{s.label}</span>
                        </td>
                        <td style={{ padding: "12px 16px", maxWidth: 320 }}>
                          {r.error_msg
                            ? <p style={{ fontSize: 12, color: "var(--red)", lineHeight: 1.4, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }} title={r.error_msg}>{r.error_msg}</p>
                            : <span style={{ color: "var(--ink-4)" }}>—</span>}
                        </td>
                        <td style={{ padding: "12px 16px", fontSize: 12, color: "var(--ink-3)", whiteSpace: "nowrap" }}>{fmtWhen(r.finished_at)}</td>
                        <td style={{ padding: "12px 16px", textAlign: "right", whiteSpace: "nowrap" }}>
                          <button onClick={() => retryIngest(r.youtube_id)}
                            style={{ fontSize: 12, fontWeight: 600, color: "var(--rose)", background: "none", border: "none", cursor: "pointer" }}>
                            Retry
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                  {ingest?.items.length === 0 && <tr><td colSpan={6} style={{ padding: "48px 0", textAlign: "center", color: "var(--ink-3)" }}>No ingest errors 🎉</td></tr>}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination */}
          {ingest && ingest.total_pages > 1 && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 14 }}>
              <button onClick={() => setInPage((p) => Math.max(1, p - 1))} disabled={inPage <= 1}
                style={{ padding: "7px 14px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, cursor: inPage <= 1 ? "not-allowed" : "pointer", opacity: inPage <= 1 ? 0.5 : 1 }}>← Prev</button>
              <span style={{ fontSize: 13, color: "var(--ink-3)", fontFamily: "JetBrains Mono" }}>{inPage} / {ingest.total_pages}</span>
              <button onClick={() => setInPage((p) => Math.min(ingest.total_pages, p + 1))} disabled={inPage >= ingest.total_pages}
                style={{ padding: "7px 14px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, cursor: inPage >= ingest.total_pages ? "not-allowed" : "pointer", opacity: inPage >= ingest.total_pages ? 0.5 : 1 }}>Next →</button>
            </div>
          )}
        </div>
      )}

      {/* ════════════════════════════════════════════════════════════════════
          TRANSLATION TAB
          ════════════════════════════════════════════════════════════════════ */}
      {tab === "translation" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

          {/* Summary cards */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
            {card("Total errors", trSummary?.total_errors ?? 0, "var(--red)")}
            {card("Cost on errored videos", trSummary != null ? `$${trSummary.cost_on_errored_videos.toFixed(4)}` : "—", "var(--ink)")}
            {card("Models affected", trSummary?.by_model.length ?? 0)}
          </div>

          {/* by_error_type chips */}
          {trSummary && trSummary.by_error_type.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              {trSummary.by_error_type.map((b) => {
                const badge = trTypeBadge(b.error_type);
                const active = trType === b.error_type;
                return (
                  <button key={b.error_type} onClick={() => { setTrType(active ? "" : b.error_type); setTrPage(1); }}
                    style={{
                      fontSize: 11, fontWeight: 600, padding: "4px 11px", borderRadius: 20, cursor: "pointer",
                      background: badge.bg, color: badge.color,
                      border: active ? `1px solid ${badge.color}` : "1px solid transparent",
                    }}>
                    {b.error_type} × {b.count}
                  </button>
                );
              })}
              {trType && (
                <button onClick={() => { setTrType(""); setTrPage(1); }}
                  style={{ fontSize: 11, fontWeight: 600, padding: "4px 11px", borderRadius: 20, cursor: "pointer", background: "var(--gray-100)", color: "var(--ink-3)", border: "1px solid var(--warm-200)" }}>
                  clear ✕
                </button>
              )}
            </div>
          )}

          {/* by_model breakdown */}
          {trSummary && trSummary.by_model.length > 0 && (
            <div style={{ background: "var(--white)", border: "1px solid var(--warm-200)", borderRadius: 12, padding: 16, boxShadow: "var(--shadow-card)" }}>
              <h2 className="font-display" style={{ fontSize: 16, color: "var(--ink)", letterSpacing: "-0.01em", marginBottom: 12 }}>By model</h2>
              <div className="scroll-x">
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr>
                      {["Provider", "Model", "Errors", "Cost"].map((h) => (
                        <th key={h} style={{ padding: "8px 12px", textAlign: "left", fontSize: 11, fontWeight: 600, color: "var(--ink-3)", letterSpacing: "0.05em", textTransform: "uppercase", background: "var(--cream)", whiteSpace: "nowrap" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {trSummary.by_model.map((row, i: number) => (
                      <tr key={`${row.provider}-${row.model ?? ""}-${i}`} style={{ borderTop: i > 0 ? "1px solid var(--warm-100)" : "none" }}>
                        <td style={{ padding: "9px 12px", fontWeight: 500, color: "var(--ink)" }}>{row.provider}</td>
                        <td style={{ padding: "9px 12px", fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--ink-3)" }}>{row.model ?? "—"}</td>
                        <td style={{ padding: "9px 12px", fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--red)" }}>{row.count.toLocaleString()}</td>
                        <td style={{ padding: "9px 12px", fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--ink)" }}>${row.cost_usd.toFixed(5)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Filter bar */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
            <input value={trQ} onChange={(e) => setTrQ(e.target.value)} placeholder="Search title or video ID…"
              style={{ flex: "1 1 220px", minWidth: 180, padding: "8px 12px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, outline: "none" }} />
            {trType && <span style={{ fontSize: 12, color: "var(--ink-3)", whiteSpace: "nowrap" }}>filtered: <strong style={{ color: "var(--ink-2)" }}>{trType}</strong></span>}
            {trErr && <span style={{ fontSize: 12, color: "var(--ink-3)", whiteSpace: "nowrap" }}>{trErr.total.toLocaleString()} results</span>}
          </div>

          {/* Translation errors table */}
          <div style={{ background: "var(--white)", borderRadius: 12, border: "1px solid var(--warm-200)", boxShadow: "var(--shadow-card)", overflow: "hidden" }}>
            <div className="scroll-x">
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, minWidth: 900 }}>
                <thead>
                  <tr>
                    {["Video", "Provider / Model", "Type", "Message", "Segment", "Cost", "When"].map((h) => (
                      <th key={h} style={{ padding: "11px 14px", textAlign: "left", fontSize: 11, fontWeight: 600, color: "var(--ink-3)", letterSpacing: "0.05em", textTransform: "uppercase", background: "var(--cream)", whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {trLoading && !trErr && <tr><td colSpan={7} style={{ padding: "48px 0", textAlign: "center", color: "var(--ink-3)" }}>Loading…</td></tr>}
                  {trErr?.items.map((r: TrErrorRow, i: number) => {
                    const badge = trTypeBadge(r.error_type);
                    return (
                      <tr key={r.id} style={{ borderTop: i > 0 ? "1px solid var(--warm-100)" : "none" }}>
                        <td style={{ padding: "11px 14px", maxWidth: 260 }}>
                          <Link href={`/editor/${r.youtube_id}`} style={{ textDecoration: "none", display: "block" }}>
                            <p style={{ fontWeight: 500, color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 260 }}>{r.title || "—"}</p>
                            <p style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2, fontFamily: "JetBrains Mono" }}>{r.youtube_id}</p>
                          </Link>
                        </td>
                        <td style={{ padding: "11px 14px", whiteSpace: "nowrap" }}>
                          <span style={{ fontSize: 11, fontWeight: 600, padding: "3px 8px", borderRadius: 20, background: "var(--gray-100)", color: "var(--ink-2)" }}>{r.provider}</span>
                          {r.model && <span style={{ display: "block", fontSize: 11, fontFamily: "JetBrains Mono", color: "var(--ink-3)", marginTop: 3 }}>{r.model}</span>}
                        </td>
                        <td style={{ padding: "11px 14px" }}>
                          <span style={{ fontSize: 11, fontWeight: 600, padding: "3px 9px", borderRadius: 20, background: badge.bg, color: badge.color, whiteSpace: "nowrap" }}>{r.error_type}</span>
                        </td>
                        <td style={{ padding: "11px 14px", maxWidth: 300, color: "var(--ink-2)" }}>
                          <span style={{ display: "block", fontSize: 12, lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 300 }} title={r.error_msg}>
                            {r.error_msg.length > 100 ? r.error_msg.slice(0, 100) + "…" : r.error_msg}
                          </span>
                        </td>
                        <td style={{ padding: "11px 14px", fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--ink-3)", whiteSpace: "nowrap" }}>
                          {r.segment_index ?? "video"}
                        </td>
                        <td style={{ padding: "11px 14px", fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--ink)", whiteSpace: "nowrap" }}>${r.cost_usd.toFixed(5)}</td>
                        <td style={{ padding: "11px 14px", fontSize: 12, color: "var(--ink-3)", whiteSpace: "nowrap" }}>{fmtWhen(r.created_at)}</td>
                      </tr>
                    );
                  })}
                  {trErr?.items.length === 0 && (
                    <tr>
                      <td colSpan={7} style={{ padding: 0 }}>
                        <div style={{ padding: "40px 28px", textAlign: "center" }}>
                          <p style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)", marginBottom: 6 }}>No translation errors logged yet.</p>
                          <p style={{ fontSize: 13, color: "var(--ink-3)", lineHeight: 1.6, maxWidth: 560, margin: "0 auto" }}>
                            Failures from translation runs (bad API key, rate limits, timeouts, malformed responses) will appear here with the model used and cost incurred.
                          </p>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination */}
          {trErr && trErr.total_pages > 1 && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 14 }}>
              <button onClick={() => setTrPage((p) => Math.max(1, p - 1))} disabled={trPage <= 1}
                style={{ padding: "7px 14px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, cursor: trPage <= 1 ? "not-allowed" : "pointer", opacity: trPage <= 1 ? 0.5 : 1 }}>← Prev</button>
              <span style={{ fontSize: 13, color: "var(--ink-3)", fontFamily: "JetBrains Mono" }}>{trPage} / {trErr.total_pages}</span>
              <button onClick={() => setTrPage((p) => Math.min(trErr.total_pages, p + 1))} disabled={trPage >= trErr.total_pages}
                style={{ padding: "7px 14px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, cursor: trPage >= trErr.total_pages ? "not-allowed" : "pointer", opacity: trPage >= trErr.total_pages ? 0.5 : 1 }}>Next →</button>
            </div>
          )}
        </div>
      )}

    </div>
  );
}
