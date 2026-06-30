"use client";
import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import axios from "axios";
import { motion, AnimatePresence } from "motion/react";

interface VideoSummary {
  id: number; youtube_id: string; title: string | null; channel: string | null;
  duration_s: number | null; status: string; segment_count: number; translated_count: number;
  fetched_at: string | null; error_msg: string | null;
}

const fetcher = (u: string) => axios.get(u).then(r => r.data);

function fmt(s: number | null) {
  if (!s) return "—";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function extractId(input: string): string | null {
  input = input.trim();
  if (/^[A-Za-z0-9_-]{11}$/.test(input)) return input;
  const s = input.match(/youtu\.be\/([A-Za-z0-9_-]{11})/);
  if (s) return s[1];
  const l = input.match(/[?&]v=([A-Za-z0-9_-]{11})/);
  if (l) return l[1];
  return null;
}

const STATUS: Record<string, { label: string; color: string; bg: string }> = {
  fetched:       { label: "Ready",       color: "var(--green)",  bg: "var(--green-light)" },
  fetching:      { label: "Fetching…",   color: "var(--gold)",   bg: "var(--gold-light)" },
  pending:       { label: "Queued",      color: "var(--ink-3)",  bg: "var(--warm-100)" },
  error:         { label: "Error",       color: "var(--red)",    bg: "var(--red-light)" },
  no_transcript: { label: "No captions", color: "var(--gold)",   bg: "var(--gold-light)" },
};

function StatusPill({ status }: { status: string }) {
  const s = STATUS[status] ?? STATUS.pending;
  return (
    <span style={{ fontSize: 11, fontWeight: 600, padding: "3px 9px", borderRadius: 20, background: s.bg, color: s.color, letterSpacing: "0.03em", whiteSpace: "nowrap" }}>{s.label}</span>
  );
}

function TranslatedCell({ done, total }: { done: number; total: number }) {
  const full = total > 0 && done >= total;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const color = full ? "var(--green)" : done > 0 ? "var(--gold)" : "var(--ink-4)";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 92 }}>
      <span style={{ fontFamily: "JetBrains Mono", fontSize: 12, color }}>
        {done.toLocaleString()}/{total.toLocaleString()}{full ? " ✓" : ""}
      </span>
      <div style={{ height: 4, width: 92, background: "var(--warm-100)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: color, transition: "width 0.4s" }} />
      </div>
    </div>
  );
}

function VideoBlock({ title, tone, dot, videos, variant, onRetry }: {
  title: string;
  tone: "green" | "red" | "amber";
  dot: string;
  videos: VideoSummary[];
  variant: "ready" | "retry" | "progress";
  onRetry: (id: string) => void;
}) {
  const toneBg = tone === "green" ? "var(--green-light)" : tone === "red" ? "var(--red-light)" : "var(--gold-light)";
  const toneFg = tone === "green" ? "var(--green)" : tone === "red" ? "var(--red)" : "var(--gold)";
  const headers = variant === "ready"
    ? ["Title", "Channel", "Duration", "Translated", "Status", ""]
    : ["Title", "Channel", "Duration", "Segments", "Status", ""];
  const emptyMsg = variant === "retry" ? "No failures — all good."
    : variant === "progress" ? "Nothing in progress." : "No fetched videos yet.";

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <span style={{ width: 9, height: 9, borderRadius: "50%", background: dot, flexShrink: 0 }} />
        <h2 className="font-display" style={{ fontSize: 18, color: "var(--ink)", letterSpacing: "-0.01em" }}>{title}</h2>
        <span style={{ fontSize: 12, fontWeight: 700, color: toneFg, background: toneBg, padding: "2px 10px", borderRadius: 20, fontFamily: "JetBrains Mono" }}>{videos.length}</span>
      </div>

      <div style={{ background: "var(--white)", borderRadius: 14, boxShadow: "var(--shadow-card)", border: "1px solid var(--warm-200)", borderTop: `2px solid ${dot}`, overflow: "hidden" }}>
        {videos.length === 0 ? (
          <div style={{ padding: "26px 0", textAlign: "center", color: "var(--ink-4)", fontSize: 13 }}>{emptyMsg}</div>
        ) : (
          <div className="scroll-x">
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, minWidth: 680 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--warm-100)" }}>
                  {headers.map((h, hi) => (
                    <th key={hi} style={{ padding: "11px 20px", textAlign: "left", fontSize: 11, fontWeight: 600, color: "var(--ink-3)", letterSpacing: "0.06em", textTransform: "uppercase", background: "var(--cream)" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {videos.map((v, i) => (
                  <tr key={v.id}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "var(--warm-50)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                    style={{ borderTop: i > 0 ? "1px solid var(--warm-100)" : "none", transition: "background 0.12s" }}>
                    <td style={{ padding: "14px 20px", maxWidth: 340 }}>
                      <p style={{ fontWeight: 600, color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{v.title || v.youtube_id}</p>
                      {v.title && <p style={{ fontSize: 11, color: "var(--ink-3)", fontFamily: "JetBrains Mono", marginTop: 2 }}>{v.youtube_id}</p>}
                    </td>
                    <td style={{ padding: "14px 20px", color: "var(--ink-2)", whiteSpace: "nowrap" }}>{v.channel || "—"}</td>
                    <td style={{ padding: "14px 20px", color: "var(--ink-2)", fontFamily: "JetBrains Mono", whiteSpace: "nowrap" }}>{fmt(v.duration_s)}</td>
                    {variant === "ready" ? (
                      <td style={{ padding: "14px 20px" }}><TranslatedCell done={v.translated_count} total={v.segment_count} /></td>
                    ) : (
                      <td style={{ padding: "14px 20px", color: "var(--ink-2)", fontFamily: "JetBrains Mono" }}>{v.segment_count.toLocaleString()}</td>
                    )}
                    <td style={{ padding: "14px 20px" }}>
                      <StatusPill status={v.status} />
                      {v.error_msg && (
                        <div style={{ fontSize: 11, color: "var(--red)", marginTop: 4, maxWidth: 260, whiteSpace: "normal", lineHeight: 1.4 }}>{v.error_msg}</div>
                      )}
                    </td>
                    <td style={{ padding: "14px 20px", textAlign: "right" }}>
                      {variant === "ready" && (
                        <Link href={`/editor/${v.youtube_id}`} style={{ fontSize: 12, fontWeight: 600, color: "var(--gold)", textDecoration: "none" }}>Edit →</Link>
                      )}
                      {variant === "retry" && (
                        <button onClick={() => onRetry(v.youtube_id)}
                          style={{ fontSize: 12, fontWeight: 600, color: "var(--red)", background: "none", border: "none", cursor: "pointer" }}>Retry</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Home() {
  const [url, setUrl]       = useState("");
  const [state, setState]   = useState<"idle"|"loading"|"queued"|"error">("idle");
  const [msg, setMsg]       = useState("");

  const { data: videos, error, isLoading, mutate } = useSWR<VideoSummary[]>(
    "/api/v1/videos", fetcher, { refreshInterval: 3000 }
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const id = extractId(url);
    if (!id) { setState("error"); setMsg("Couldn't find a YouTube video ID."); return; }
    setState("loading"); setMsg("");
    try {
      const { data } = await axios.post("/api/v1/ingest/", { youtube_id: id });
      setState("queued"); setMsg(data.message); setUrl(""); mutate();
    } catch (err: unknown) {
      setState("error");
      const m = axios.isAxiosError(err) ? err.response?.data?.detail ?? err.message : String(err);
      setMsg(typeof m === "string" ? m : JSON.stringify(m));
    }
  }

  async function retry(id: string) {
    try { await axios.post("/api/v1/ingest/", { youtube_id: id }); } catch { /* surfaced via list refresh */ }
    mutate();
  }

  const all      = videos ?? [];
  const ready    = all.filter(v => v.status === "fetched");
  const retryList = all.filter(v => v.status === "error" || v.status === "no_transcript");
  const progress = all.filter(v => v.status === "pending" || v.status === "fetching");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 44 }}>

      {/* Hero intake */}
      <div style={{ textAlign: "center", paddingTop: 24 }}>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: [0.22,1,0.36,1] }}>
          <p style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.12em", color: "var(--gold)", textTransform: "uppercase", marginBottom: 12 }}>
            Telugu · Christian · Theology
          </p>
          <h1 className="font-display" style={{ fontSize: 40, color: "var(--ink)", lineHeight: 1.15, letterSpacing: "-0.02em", marginBottom: 8 }}>
            Translation Engine
          </h1>
          <p style={{ fontSize: 15, color: "var(--ink-2)", marginBottom: 36, maxWidth: 460, margin: "0 auto 36px" }}>
            Paste a YouTube sermon URL. Extract captions, translate, review, export fine-tuning data.
          </p>

          {/* URL input — hero style */}
          <form onSubmit={handleSubmit} style={{ maxWidth: 580, margin: "0 auto", display: "flex", gap: 10, padding: "6px 6px 6px 20px", background: "var(--white)", borderRadius: 14, boxShadow: "0 4px 24px rgba(0,0,0,0.08), 0 1px 3px rgba(0,0,0,0.06)", border: "1px solid var(--warm-200)" }}>
            <input
              type="text" value={url}
              onChange={(e) => { setUrl(e.target.value); setState("idle"); }}
              placeholder="https://youtube.com/watch?v=… or video ID"
              style={{ flex: 1, border: "none", outline: "none", fontSize: 14, color: "var(--ink)", background: "transparent", fontFamily: "Plus Jakarta Sans" }}
            />
            <motion.button type="submit"
              disabled={state === "loading" || !url.trim()}
              whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
              style={{ padding: "10px 22px", borderRadius: 10, border: "none", background: "var(--ink)", color: "var(--white)", fontSize: 13, fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap", fontFamily: "Plus Jakarta Sans", opacity: (state === "loading" || !url.trim()) ? 0.5 : 1 }}>
              {state === "loading" ? "Adding…" : "Add video →"}
            </motion.button>
          </form>

          <AnimatePresence>
            {state === "queued" && (
              <motion.p key="ok" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                style={{ marginTop: 12, fontSize: 13, color: "var(--green)" }}>✓ {msg}</motion.p>
            )}
            {state === "error" && (
              <motion.p key="err" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                style={{ marginTop: 12, fontSize: 13, color: "var(--red)" }}>✗ {msg}</motion.p>
            )}
          </AnimatePresence>
        </motion.div>
      </div>

      {/* Video blocks */}
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.1, ease: [0.22,1,0.36,1] }}
        style={{ display: "flex", flexDirection: "column", gap: 30 }}>

        {isLoading && !videos && (
          <div style={{ padding: "60px 0", textAlign: "center", color: "var(--ink-3)", fontSize: 13, background: "var(--white)", borderRadius: 14, border: "1px solid var(--warm-200)" }}>Loading…</div>
        )}
        {error && (
          <div style={{ padding: "48px 0", textAlign: "center", color: "var(--red)", fontSize: 13, background: "var(--white)", borderRadius: 14, border: "1px solid var(--warm-200)" }}>Backend not reachable.</div>
        )}
        {videos && all.length === 0 && (
          <div style={{ padding: "72px 0", textAlign: "center", background: "var(--white)", borderRadius: 14, border: "1px solid var(--warm-200)" }}>
            <p className="font-display" style={{ fontSize: 18, color: "var(--ink-3)", marginBottom: 6 }}>No videos yet</p>
            <p style={{ fontSize: 13, color: "var(--ink-4)" }}>Paste a YouTube URL above to get started.</p>
          </div>
        )}

        {videos && all.length > 0 && (
          <>
            <VideoBlock title="Ready" tone="green" dot="var(--green)" videos={ready} variant="ready" onRetry={retry} />
            <VideoBlock title="Needs retry" tone="red" dot="var(--red)" videos={retryList} variant="retry" onRetry={retry} />
            {progress.length > 0 && (
              <VideoBlock title="In progress" tone="amber" dot="var(--gold)" videos={progress} variant="progress" onRetry={retry} />
            )}
          </>
        )}
      </motion.div>
    </div>
  );
}
