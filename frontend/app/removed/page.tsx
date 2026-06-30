"use client";
import { useEffect, useState } from "react";
import useSWR from "swr";
import axios from "axios";

const fetcher = (u: string) => axios.get(u).then((r) => r.data);

// ── Interfaces ────────────────────────────────────────────────────────────────

interface RemovedRow {
  youtube_id: string;
  title: string | null;
  scope: string;
  reason: string | null;
  excluded_at: string | null;
  status: string;
  segment_count: number;
  translated_count: number;
}
interface RemovedResp {
  items: RemovedRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  counts: { ingest: number; translation: number };
}

// ── Constants ─────────────────────────────────────────────────────────────────

const SCOPE_BADGE: Record<string, { label: string; color: string; bg: string }> = {
  ingest:      { label: "ingest",      color: "var(--amber)", bg: "var(--amber-light)" },
  translation: { label: "translation", color: "var(--gold)",  bg: "var(--gold-light)" },
};

const SCOPE_FILTERS = ["all", "ingest", "translation"];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function RemovedPage() {
  const [scope, setScope] = useState("all");
  const [q, setQ] = useState("");
  const [qDeb, setQDeb] = useState("");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState<string | null>(null);
  const pageSize = 50;

  useEffect(() => {
    const t = setTimeout(() => { setQDeb(q); setPage(1); }, 350);
    return () => clearTimeout(t);
  }, [q]);

  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (scope !== "all") params.set("scope", scope);
  if (qDeb) params.set("q", qDeb);

  const { data, isLoading, mutate } = useSWR<RemovedResp>(
    `/api/v1/removed?${params.toString()}`, fetcher,
    { refreshInterval: 0, keepPreviousData: true }
  );

  const counts = data?.counts ?? { ingest: 0, translation: 0 };

  async function restore(youtubeId: string) {
    setBusy(youtubeId);
    try { await axios.post(`/api/v1/videos/${youtubeId}/restore`); } catch {}
    finally { setBusy(null); }
    mutate();
  }

  async function deletePermanently(youtubeId: string) {
    if (!window.confirm(`Permanently delete ${youtubeId} and all its data? This cannot be undone.`)) return;
    setBusy(youtubeId);
    try { await axios.delete(`/api/v1/videos/${youtubeId}`); } catch {}
    finally { setBusy(null); }
    mutate();
  }

  const card = (label: string, value: number | string, color = "var(--ink)") => (
    <div style={{ flex: "1 1 160px", minWidth: 140, background: "var(--white)", border: "1px solid var(--warm-200)", borderRadius: 12, padding: "14px 16px", boxShadow: "var(--shadow-card)" }}>
      <p style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</p>
      <p style={{ fontSize: 24, fontWeight: 700, color, fontFamily: "JetBrains Mono", marginTop: 4 }}>{typeof value === "number" ? value.toLocaleString() : value}</p>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

      {/* Page title */}
      <div>
        <h1 className="font-display" style={{ fontSize: 26, color: "var(--ink)", letterSpacing: "-0.01em" }}>Removed</h1>
        <p style={{ fontSize: 13, color: "var(--ink-3)", marginTop: 4 }}>
          Videos removed from ingest or translation. Restore them or delete permanently.
        </p>
      </div>

      {/* Summary cards */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        {card("From ingest", counts.ingest, "var(--amber)")}
        {card("From translation", counts.translation, "var(--gold)")}
      </div>

      {/* Filter bar */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
        <select value={scope} onChange={(e) => { setScope(e.target.value); setPage(1); }}
          style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, color: "var(--ink)" }}>
          {SCOPE_FILTERS.map((f) => <option key={f} value={f}>{f === "all" ? "All scopes" : (SCOPE_BADGE[f]?.label ?? f)}</option>)}
        </select>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title or video ID…"
          style={{ flex: "1 1 220px", minWidth: 180, padding: "8px 12px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, outline: "none" }} />
        {data && <span style={{ fontSize: 12, color: "var(--ink-3)", whiteSpace: "nowrap" }}>{data.total.toLocaleString()} results</span>}
      </div>

      {/* Table */}
      <div style={{ background: "var(--white)", borderRadius: 12, border: "1px solid var(--warm-200)", boxShadow: "var(--shadow-card)", overflow: "hidden" }}>
        <div className="scroll-x">
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, minWidth: 820 }}>
            <thead>
              <tr>
                {["Title", "Video ID", "Scope", "Reason", "Removed", "Segments", "Actions"].map((h) => (
                  <th key={h} style={{ padding: "11px 16px", textAlign: "left", fontSize: 11, fontWeight: 600, color: "var(--ink-3)", letterSpacing: "0.05em", textTransform: "uppercase", background: "var(--cream)", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading && !data && <tr><td colSpan={7} style={{ padding: "48px 0", textAlign: "center", color: "var(--ink-3)" }}>Loading…</td></tr>}
              {data?.items.map((r: RemovedRow, i: number) => {
                const badge = SCOPE_BADGE[r.scope] ?? { label: r.scope, color: "var(--gray-500)", bg: "var(--gray-100)" };
                const rowBusy = busy === r.youtube_id;
                return (
                  <tr key={`${r.youtube_id}-${r.scope}`} style={{ borderTop: i > 0 ? "1px solid var(--warm-100)" : "none", opacity: rowBusy ? 0.5 : 1 }}>
                    <td style={{ padding: "12px 16px", maxWidth: 320 }}>
                      <p style={{ fontWeight: 500, color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 320 }}>{r.title || "—"}</p>
                    </td>
                    <td style={{ padding: "12px 16px", fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--ink-3)", whiteSpace: "nowrap" }}>
                      <a href={`https://youtu.be/${r.youtube_id}`} target="_blank" rel="noreferrer" style={{ color: "var(--ink-3)", textDecoration: "none" }}>{r.youtube_id}</a>
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <span style={{ fontSize: 11, fontWeight: 600, padding: "3px 9px", borderRadius: 20, background: badge.bg, color: badge.color, whiteSpace: "nowrap" }}>{badge.label}</span>
                    </td>
                    <td style={{ padding: "12px 16px", maxWidth: 260, color: "var(--ink-3)" }}>
                      <span style={{ whiteSpace: "normal", lineHeight: 1.4 }}>{r.reason || "—"}</span>
                    </td>
                    <td style={{ padding: "12px 16px", fontSize: 12, color: "var(--ink-3)", whiteSpace: "nowrap" }}>
                      {r.excluded_at ? new Date(r.excluded_at).toLocaleString() : "—"}
                    </td>
                    <td style={{ padding: "12px 16px", fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--ink-2)" }}>{r.segment_count || "—"}</td>
                    <td style={{ padding: "12px 16px", whiteSpace: "nowrap" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                        <button onClick={() => restore(r.youtube_id)} disabled={rowBusy}
                          style={{ fontSize: 12, fontWeight: 600, color: "var(--green)", background: "none", border: "none", cursor: rowBusy ? "not-allowed" : "pointer", opacity: rowBusy ? 0.5 : 1 }}>
                          Restore
                        </button>
                        <button onClick={() => deletePermanently(r.youtube_id)} disabled={rowBusy}
                          style={{ fontSize: 12, fontWeight: 600, color: "var(--red)", background: "none", border: "none", cursor: rowBusy ? "not-allowed" : "pointer", opacity: rowBusy ? 0.5 : 1 }}>
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {data?.items.length === 0 && <tr><td colSpan={7} style={{ padding: "48px 0", textAlign: "center", color: "var(--ink-3)" }}>Nothing removed — the bin is empty.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {data && data.total_pages > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 14 }}>
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}
            style={{ padding: "7px 14px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, cursor: page <= 1 ? "not-allowed" : "pointer", opacity: page <= 1 ? 0.5 : 1 }}>← Prev</button>
          <span style={{ fontSize: 13, color: "var(--ink-3)", fontFamily: "JetBrains Mono" }}>{page} / {data.total_pages}</span>
          <button onClick={() => setPage((p) => Math.min(data.total_pages, p + 1))} disabled={page >= data.total_pages}
            style={{ padding: "7px 14px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, cursor: page >= data.total_pages ? "not-allowed" : "pointer", opacity: page >= data.total_pages ? 0.5 : 1 }}>Next →</button>
        </div>
      )}
    </div>
  );
}
