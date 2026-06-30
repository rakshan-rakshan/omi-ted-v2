"use client";
import { useEffect, useState } from "react";
import useSWR from "swr";
import axios from "axios";
import Link from "next/link";
import { motion } from "motion/react";
import RemoveDialog from "@/components/RemoveDialog";

const fetcher = (u: string) => axios.get(u).then((r) => r.data);

interface RunState {
  running: boolean; mode: string | null; total: number; processed: number;
  succeeded: number; failed: number; skipped: number; current: string | null;
  started_at: string | null;
}
interface Summary {
  total: number; fetched: number; percent: number;
  counts: Record<string, number>; csv_total: number; run: RunState;
}
interface UniRow {
  youtube_id: string; title: string | null; status: string;
  segment_count: number; translated_count: number; error_msg: string | null;
}
interface UniPage {
  total: number; page: number; page_size: number; total_pages: number; items: UniRow[];
}

const STATUS: Record<string, { label: string; color: string; bg: string }> = {
  fetched:       { label: "Fetched",     color: "var(--green)",    bg: "var(--green-light)" },
  fetching:      { label: "Fetching…",   color: "var(--amber)",    bg: "var(--amber-light)" },
  pending:       { label: "Queued",      color: "var(--gray-600)", bg: "var(--gray-100)" },
  error:         { label: "Error",       color: "var(--red)",      bg: "var(--red-light)" },
  no_transcript: { label: "No captions", color: "var(--amber)",    bg: "var(--amber-light)" },
  not_attempted: { label: "Not run",     color: "var(--gray-500)", bg: "var(--gray-50)" },
};

const FILTERS = ["all", "not_attempted", "fetched", "error", "no_transcript", "pending", "fetching"];

function TrCell({ done, total }: { done: number; total: number }) {
  if (!total) return <span style={{ color: "var(--ink-4)" }}>—</span>;
  const full = done >= total;
  const pct = Math.round((done / total) * 100);
  const color = full ? "var(--green)" : done > 0 ? "var(--gold)" : "var(--ink-4)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ fontFamily: "JetBrains Mono", fontSize: 12, color, whiteSpace: "nowrap" }}>{done}/{total}{full ? " ✓" : ""}</span>
      <div style={{ height: 4, width: 48, background: "var(--warm-100)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [status, setStatus] = useState("all");
  const [q, setQ] = useState("");
  const [qDeb, setQDeb] = useState("");
  const [page, setPage] = useState(1);
  const [removeId, setRemoveId] = useState<string | null>(null);
  const [removeTitle, setRemoveTitle] = useState<string | null>(null);
  const pageSize = 50;

  const { data: summary, mutate: mutateSummary } = useSWR<Summary>(
    "/api/v1/ingest/summary", fetcher, { refreshInterval: 5000 }
  );
  const running = !!summary?.run?.running;

  const { data: runLive } = useSWR<RunState>(
    running ? "/api/v1/ingest/run/status" : null, fetcher, { refreshInterval: 2000 }
  );
  const run = runLive ?? summary?.run;

  useEffect(() => {
    const t = setTimeout(() => { setQDeb(q); setPage(1); }, 350);
    return () => clearTimeout(t);
  }, [q]);

  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (status !== "all") params.set("status", status);
  if (qDeb) params.set("q", qDeb);
  const { data: uni, isLoading, mutate: mutateUni } = useSWR<UniPage>(
    `/api/v1/ingest/universe?${params.toString()}`, fetcher,
    { refreshInterval: running ? 5000 : 0, keepPreviousData: true }
  );

  const c = summary?.counts ?? {};
  async function startRun(mode: "new" | "retry") {
    try { await axios.post("/api/v1/ingest/run", { mode }); } catch {}
    mutateSummary();
  }
  async function stopRun() { try { await axios.post("/api/v1/ingest/run/stop"); } catch {}; mutateSummary(); }
  async function retryOne(id: string) {
    try { await axios.post("/api/v1/ingest/", { youtube_id: id }); } catch {}
    mutateUni(); mutateSummary();
  }

  const card = (label: string, value: number | string, color = "var(--ink)") => (
    <div style={{ flex: "1 1 130px", minWidth: 120, background: "var(--white)", border: "1px solid var(--warm-200)", borderRadius: 12, padding: "14px 16px", boxShadow: "var(--shadow-card)" }}>
      <p style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</p>
      <p style={{ fontSize: 24, fontWeight: 700, color, fontFamily: "JetBrains Mono", marginTop: 4 }}>{typeof value === "number" ? value.toLocaleString() : value}</p>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div>
        <h1 className="font-display" style={{ fontSize: 26, color: "var(--ink)", letterSpacing: "-0.01em" }}>Ingest Dashboard</h1>
        <p style={{ fontSize: 13, color: "var(--ink-3)", marginTop: 4 }}>
          {summary ? `${summary.fetched.toLocaleString()} of ${summary.total.toLocaleString()} videos fetched (${summary.percent}%)` : "Loading…"}
        </p>
      </div>

      {/* Progress bar */}
      <div style={{ height: 10, background: "var(--warm-100)", borderRadius: 6, overflow: "hidden" }}>
        <motion.div initial={{ width: 0 }} animate={{ width: `${summary?.percent ?? 0}%` }}
          transition={{ duration: 0.5 }} style={{ height: "100%", background: "var(--green)" }} />
      </div>

      {/* Summary cards */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        {card("Fetched", c.fetched ?? 0, "var(--green)")}
        {card("Not run", c.not_attempted ?? 0, "var(--gray-500)")}
        {card("Errors", c.error ?? 0, "var(--red)")}
        {card("No captions", c.no_transcript ?? 0, "var(--amber)")}
        {card("In flight", (c.pending ?? 0) + (c.fetching ?? 0), "var(--amber)")}
        {card("Total URLs", summary?.total ?? 0)}
      </div>

      {/* Action bar / live run */}
      <div style={{ background: "var(--white)", border: "1px solid var(--warm-200)", borderRadius: 12, padding: 16, boxShadow: "var(--shadow-card)" }}>
        {!running ? (
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
            <button onClick={() => startRun("new")} disabled={(c.not_attempted ?? 0) === 0}
              style={{ padding: "10px 18px", borderRadius: 10, border: "none", background: "var(--ink)", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer", opacity: (c.not_attempted ?? 0) === 0 ? 0.5 : 1 }}>
              ▶ Run new ({(c.not_attempted ?? 0).toLocaleString()})
            </button>
            <button onClick={() => startRun("retry")} disabled={(c.error ?? 0) === 0}
              style={{ padding: "10px 18px", borderRadius: 10, border: "1px solid var(--red-border)", background: "var(--red-light)", color: "var(--red)", fontSize: 13, fontWeight: 600, cursor: "pointer", opacity: (c.error ?? 0) === 0 ? 0.5 : 1 }}>
              ↻ Retry failed ({(c.error ?? 0).toLocaleString()})
            </button>
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>
              Runs are paced for YouTube limits. Large runs need <code>YTDLP_COOKIES_FILE</code> configured.
            </span>
          </div>
        ) : (
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--green)", animation: "pulse 1.4s infinite" }} />
              <strong style={{ fontSize: 14, color: "var(--ink)" }}>Running ({run?.mode})</strong>
            </div>
            <span style={{ fontFamily: "JetBrains Mono", fontSize: 13, color: "var(--ink-2)" }}>
              {run?.processed}/{run?.total} · ✓{run?.succeeded} ✗{run?.failed} {run?.skipped ? `· skip ${run.skipped}` : ""}
            </span>
            {run?.current && <span style={{ fontSize: 12, color: "var(--ink-3)" }}>current: <code>{run.current}</code></span>}
            <button onClick={stopRun} style={{ padding: "8px 16px", borderRadius: 10, border: "1px solid var(--red-border)", background: "var(--red-light)", color: "var(--red)", fontSize: 13, fontWeight: 600, cursor: "pointer", marginLeft: "auto" }}>■ Stop</button>
          </div>
        )}
      </div>

      {/* Filter bar */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}
          style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, color: "var(--ink)" }}>
          {FILTERS.map((f) => <option key={f} value={f}>{f === "all" ? "All statuses" : (STATUS[f]?.label ?? f)}</option>)}
        </select>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title or video ID…"
          style={{ flex: "1 1 220px", minWidth: 180, padding: "8px 12px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, outline: "none" }} />
        {uni && <span style={{ fontSize: 12, color: "var(--ink-3)", whiteSpace: "nowrap" }}>{uni.total.toLocaleString()} results</span>}
      </div>

      {/* Universe table */}
      <div style={{ background: "var(--white)", borderRadius: 12, border: "1px solid var(--warm-200)", boxShadow: "var(--shadow-card)", overflow: "hidden" }}>
        <div className="scroll-x">
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, minWidth: 640 }}>
            <thead>
              <tr>
                {["Title", "Video ID", "Status", "Segments", "Translated", ""].map((h) => (
                  <th key={h} style={{ padding: "11px 16px", textAlign: "left", fontSize: 11, fontWeight: 600, color: "var(--ink-3)", letterSpacing: "0.05em", textTransform: "uppercase", background: "var(--cream)", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading && !uni && <tr><td colSpan={6} style={{ padding: "48px 0", textAlign: "center", color: "var(--ink-3)" }}>Loading…</td></tr>}
              {uni?.items.map((r, i) => {
                const s = STATUS[r.status] ?? STATUS.not_attempted;
                return (
                  <tr key={r.youtube_id} style={{ borderTop: i > 0 ? "1px solid var(--warm-100)" : "none" }}>
                    <td style={{ padding: "12px 16px", maxWidth: 360 }}>
                      <p style={{ fontWeight: 500, color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 360 }}>{r.title || "—"}</p>
                      {r.error_msg && <p style={{ fontSize: 11, color: "var(--red)", marginTop: 3, whiteSpace: "normal", lineHeight: 1.4 }}>{r.error_msg.slice(0, 120)}</p>}
                    </td>
                    <td style={{ padding: "12px 16px", fontFamily: "JetBrains Mono", color: "var(--ink-3)", whiteSpace: "nowrap" }}>
                      <a href={`https://youtu.be/${r.youtube_id}`} target="_blank" rel="noreferrer" style={{ color: "var(--ink-3)", textDecoration: "none" }}>{r.youtube_id}</a>
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <span style={{ fontSize: 11, fontWeight: 600, padding: "3px 9px", borderRadius: 20, background: s.bg, color: s.color, whiteSpace: "nowrap" }}>{s.label}</span>
                    </td>
                    <td style={{ padding: "12px 16px", fontFamily: "JetBrains Mono", color: "var(--ink-2)" }}>{r.segment_count || ""}</td>
                    <td style={{ padding: "12px 16px" }}>
                      {r.status === "fetched" ? <TrCell done={r.translated_count} total={r.segment_count} /> : <span style={{ color: "var(--ink-4)" }}>—</span>}
                    </td>
                    <td style={{ padding: "12px 16px", textAlign: "right", whiteSpace: "nowrap" }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 12 }}>
                        {r.status === "fetched" && <Link href={`/editor/${r.youtube_id}`} style={{ fontSize: 12, fontWeight: 600, color: "var(--gold)", textDecoration: "none" }}>Edit →</Link>}
                        {(r.status === "error" || r.status === "no_transcript" || r.status === "not_attempted") && (
                          <button onClick={() => retryOne(r.youtube_id)} disabled={running}
                            style={{ fontSize: 12, fontWeight: 600, color: "var(--rose)", background: "none", border: "none", cursor: running ? "not-allowed" : "pointer", opacity: running ? 0.5 : 1 }}>
                            {r.status === "not_attempted" ? "Run" : "Retry"}
                          </button>
                        )}
                        {r.status !== "not_attempted" && (
                          <button onClick={() => { setRemoveId(r.youtube_id); setRemoveTitle(r.title); }}
                            style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-4)", background: "none", border: "none", cursor: "pointer" }}
                            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--red)")}
                            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--ink-4)")}>
                            Remove
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {uni?.items.length === 0 && <tr><td colSpan={6} style={{ padding: "48px 0", textAlign: "center", color: "var(--ink-3)" }}>No matching videos.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {uni && uni.total_pages > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 14 }}>
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}
            style={{ padding: "7px 14px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, cursor: page <= 1 ? "not-allowed" : "pointer", opacity: page <= 1 ? 0.5 : 1 }}>← Prev</button>
          <span style={{ fontSize: 13, color: "var(--ink-3)", fontFamily: "JetBrains Mono" }}>{page} / {uni.total_pages}</span>
          <button onClick={() => setPage((p) => Math.min(uni.total_pages, p + 1))} disabled={page >= uni.total_pages}
            style={{ padding: "7px 14px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, cursor: page >= uni.total_pages ? "not-allowed" : "pointer", opacity: page >= uni.total_pages ? 0.5 : 1 }}>Next →</button>
        </div>
      )}

      <RemoveDialog
        open={!!removeId}
        youtubeId={removeId}
        title={removeTitle}
        scope="ingest"
        onClose={() => { setRemoveId(null); setRemoveTitle(null); }}
        onRemoved={() => { mutateUni(); mutateSummary(); }}
      />
    </div>
  );
}
