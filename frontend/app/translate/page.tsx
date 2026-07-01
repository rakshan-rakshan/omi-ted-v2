"use client";
import { useEffect, useState } from "react";
import useSWR from "swr";
import axios from "axios";
import Link from "next/link";
import { motion } from "motion/react";
import RemoveDialog from "@/components/RemoveDialog";

const fetcher = (u: string) => axios.get(u).then((r) => r.data);

// ── Interfaces ────────────────────────────────────────────────────────────────

interface TrRunState {
  running: boolean; mode: string | null; total: number; processed: number;
  translated: number; errors: number; skipped: number; current: string | null;
  provider: string | null; model: string | null; started_at: string | null;
  cost_usd?: number; prompt_tokens?: number; completion_tokens?: number;
}
interface TranslationSummary {
  translated_videos: number; partial_videos: number; untranslated_videos: number;
  total_segments: number; translated_segments: number; percent: number;
}
interface Summary {
  total: number; fetched: number; percent: number;
  counts: Record<string, number>; translation: TranslationSummary;
}
interface ModelOption {
  provider: string; model: string | null; label: string; free: boolean;
  prompt_per_mtok?: number; completion_per_mtok?: number; inr_per_char?: number;
  unit: string;
}
interface OverviewResp {
  total_cost_usd: number; total_translated_segs: number;
  by_model: Array<{ provider: string; model: string | null; cost_usd: number; segments: number }>;
  cache_saved_usd: number; recent_runs: unknown[];
}
interface FlagsResp {
  flags: Array<{
    segment_id: number; video_id: number; youtube_id: string; issue: string;
    te_original: string; en_final: string | null; quality_score: number | null;
  }>;
  total: number;
}
interface CreditsResp {
  openrouter: { limit: number | null; usage: number; remaining: number | null; is_free_tier: boolean; error: string | null } | null;
  sarvam: { note: string };
}
interface UniRow {
  youtube_id: string; title: string | null; status: string;
  segment_count: number; translated_count: number; error_msg: string | null;
}
interface UniPage {
  total: number; page: number; page_size: number; total_pages: number; items: UniRow[];
}

// ── Constants ─────────────────────────────────────────────────────────────────

const STATUS: Record<string, { label: string; color: string; bg: string }> = {
  fetched:       { label: "Fetched",     color: "var(--green)",    bg: "var(--green-light)" },
  fetching:      { label: "Fetching…",   color: "var(--amber)",    bg: "var(--amber-light)" },
  pending:       { label: "Queued",      color: "var(--gray-600)", bg: "var(--gray-100)" },
  error:         { label: "Error",       color: "var(--red)",      bg: "var(--red-light)" },
  no_transcript: { label: "No captions", color: "var(--amber)",    bg: "var(--amber-light)" },
  not_attempted: { label: "Not run",     color: "var(--gray-500)", bg: "var(--gray-50)" },
  translated:    { label: "Translated",  color: "var(--green)",    bg: "var(--green-light)" },
  partial:       { label: "Partial",     color: "var(--amber)",    bg: "var(--amber-light)" },
  untranslated:  { label: "Untranslated",color: "var(--gray-500)", bg: "var(--gray-100)" },
};

const CORPUS_FILTERS = ["all", "fetched", "partial", "untranslated"];

const FLAG_BADGE: Record<string, { color: string; bg: string }> = {
  empty:        { color: "var(--red)",   bg: "var(--red-light)" },
  identical:    { color: "var(--amber)", bg: "var(--amber-light)" },
  length_ratio: { color: "var(--amber)", bg: "var(--amber-light)" },
  unreviewed:   { color: "var(--gray-500)", bg: "var(--gray-100)" },
};

// ── Sub-components ────────────────────────────────────────────────────────────

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

// ── Main page ─────────────────────────────────────────────────────────────────

export default function TranslatePage() {
  // corpus table state
  const [corpusFilter, setCorpusFilter] = useState("all");
  const [corpusQ, setCorpusQ] = useState("");
  const [corpusQDeb, setCorpusQDeb] = useState("");
  const [corpusPage, setCorpusPage] = useState(1);
  const [removeId, setRemoveId] = useState<string | null>(null);
  const [removeTitle, setRemoveTitle] = useState<string | null>(null);
  const corpusPageSize = 50;

  // model selector state (mirrors dashboard)
  const [sel, setSel] = useState("");
  const [showAdv, setShowAdv] = useState(false);
  const [batchSize, setBatchSize] = useState<number | "">("");
  const [vconc, setVconc] = useState<number | "">("");

  // ── SWR hooks ──────────────────────────────────────────────────────────────

  const { data: summary } = useSWR<Summary>(
    "/api/v1/ingest/summary", fetcher, { refreshInterval: 5000 }
  );

  const { data: trRun, mutate: mutateTr } = useSWR<TrRunState>(
    "/api/v1/batch/translate/run/status", fetcher,
    { refreshInterval: 5000 }  // will tighten below once trRunning is known
  );
  const trRunning = !!trRun?.running;

  // Re-poll faster while running — swap key so SWR creates a separate cache entry when running
  const { data: trRunLive } = useSWR<TrRunState>(
    trRunning ? "/api/v1/batch/translate/run/status?live=1" : null,
    fetcher, { refreshInterval: 2000 }
  );
  const liveRun = trRunLive ?? trRun;

  const { data: models } = useSWR<{ options: ModelOption[] }>(
    "/api/v1/models", fetcher, { revalidateOnFocus: false }
  );
  const opts = models?.options ?? [];
  const selOpt = opts.find((o) => `${o.provider}::${o.model ?? ""}` === sel) ?? null;

  const { data: overview, mutate: mutateOverview } = useSWR<OverviewResp>(
    "/api/v1/translation/overview", fetcher,
    { refreshInterval: trRunning ? 0 : 10000 }
  );

  const { data: flagsData, mutate: mutateFlags } = useSWR<FlagsResp>(
    "/api/v1/translation/flags", fetcher, { revalidateOnFocus: false }
  );

  const { data: credits, mutate: mutateCredits } = useSWR<CreditsResp>(
    "/api/v1/credits", fetcher, { revalidateOnFocus: false }
  );

  // Corpus universe table
  const corpusParams = new URLSearchParams({ status: "fetched", page: String(corpusPage), page_size: String(corpusPageSize) });
  if (corpusFilter !== "all") corpusParams.set("status", corpusFilter);
  if (corpusQDeb) corpusParams.set("q", corpusQDeb);
  const { data: uni, mutate: mutateUni } = useSWR<UniPage>(
    `/api/v1/ingest/universe?${corpusParams.toString()}`, fetcher,
    { refreshInterval: trRunning ? 3000 : 0, keepPreviousData: true }
  );

  // ── Side effects ───────────────────────────────────────────────────────────

  useEffect(() => {
    const t = setTimeout(() => { setCorpusQDeb(corpusQ); setCorpusPage(1); }, 350);
    return () => clearTimeout(t);
  }, [corpusQ]);

  // ── Derived values ─────────────────────────────────────────────────────────

  const tr = summary?.translation;
  const pendingSegs = tr ? tr.total_segments - tr.translated_segments : 0;

  function estimate(): string {
    if (!selOpt || selOpt.free || selOpt.provider === "youtube") return "Free";
    if (selOpt.provider === "sarvam" && selOpt.inr_per_char) {
      const inr = pendingSegs * 150 * selOpt.inr_per_char;
      return `~₹${inr.toFixed(0)} · ${pendingSegs.toLocaleString()} pending segs`;
    }
    if (selOpt.provider === "openrouter") {
      const usd = pendingSegs * (70 * (selOpt.prompt_per_mtok ?? 0) + 60 * (selOpt.completion_per_mtok ?? 0)) / 1e6;
      return `~$${usd.toFixed(2)} · ${pendingSegs.toLocaleString()} pending segs`;
    }
    return "";
  }

  // ETA calculation
  function eta(): string | null {
    if (!liveRun || !liveRun.running || !liveRun.started_at) return null;
    const processed = liveRun.processed;
    const total = liveRun.total;
    if (processed <= 0 || total <= 0) return null;
    const elapsed = (Date.now() - new Date(liveRun.started_at).getTime()) / 1000;
    if (elapsed <= 0) return null;
    const remaining = total - processed;
    const etaSec = remaining * (elapsed / processed);
    if (etaSec < 60) return `~${Math.round(etaSec)}s`;
    if (etaSec < 3600) return `~${Math.round(etaSec / 60)}m`;
    return `~${(etaSec / 3600).toFixed(1)}h`;
  }

  // ── Actions ────────────────────────────────────────────────────────────────

  async function startTranslate(mode: "pending" | "all") {
    const body: Record<string, unknown> = { mode };
    if (selOpt) { body.provider = selOpt.provider; if (selOpt.model) body.model = selOpt.model; }
    if (batchSize !== "") body.batch_size = batchSize;
    if (vconc !== "") body.video_concurrency = vconc;
    try { await axios.post("/api/v1/batch/translate/run", body); } catch {}
    mutateTr();
  }

  async function stopTranslate() {
    try { await axios.post("/api/v1/batch/translate/run/stop"); } catch {}
    mutateTr();
  }

  async function translateOne(youtubeId: string) {
    const body: Record<string, unknown> = { youtube_id: youtubeId };
    if (selOpt) { body.provider = selOpt.provider; if (selOpt.model) body.model = selOpt.model; }
    await axios.post("/api/v1/batch/translate", body).catch(() => {});
    mutateUni();
  }

  // ── Shared card helper ─────────────────────────────────────────────────────

  const card = (
    label: string,
    value: number | string,
    color = "var(--ink)",
    opts: { big?: boolean; sub?: string } = {},
  ) => {
    const text = typeof value === "number" ? value.toLocaleString() : value;
    // Hero card (big) is prominent; the rest are compact. Font shrinks for long strings.
    const len = String(text).length;
    const valueSize = opts.big
      ? (len <= 11 ? 30 : len <= 16 ? 26 : 22)
      : (len <= 7 ? 19 : len <= 11 ? 16 : 14);
    return (
      <div style={{
        flex: opts.big ? "2 1 250px" : "1 1 120px",
        minWidth: opts.big ? 230 : 108,
        background: "var(--white)", border: "1px solid var(--warm-200)", borderRadius: 12,
        padding: opts.big ? "16px 20px" : "12px 14px", boxShadow: "var(--shadow-card)", overflow: "hidden",
      }}>
        <p style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</p>
        <p style={{ fontSize: valueSize, fontWeight: 700, color, fontFamily: "JetBrains Mono", marginTop: 4, lineHeight: 1.2, overflowWrap: "break-word" }}>{text}</p>
        {opts.sub && <p style={{ fontSize: 11, color: "var(--ink-3)", fontFamily: "JetBrains Mono", marginTop: 2 }}>{opts.sub}</p>}
      </div>
    );
  };

  const etaStr = eta();

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

      {/* Page title */}
      <div>
        <h1 className="font-display" style={{ fontSize: 26, color: "var(--ink)", letterSpacing: "-0.01em" }}>Translation Control</h1>
        <p style={{ fontSize: 13, color: "var(--ink-3)", marginTop: 4 }}>
          {tr ? `${tr.translated_segments.toLocaleString()} of ${tr.total_segments.toLocaleString()} segments translated (${tr.percent}%)` : "Loading…"}
        </p>
      </div>

      {/* ── SECTION 1: Headline stats ───────────────────────────────────────── */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "stretch" }}>
        {card("Segs done", tr ? `${tr.translated_segments.toLocaleString()} / ${tr.total_segments.toLocaleString()}` : "—", "var(--gold)", { big: true, sub: tr ? `${tr.percent}% done` : undefined })}
        {card("Translated", tr?.translated_videos ?? "—", "var(--green)")}
        {card("Partial", tr?.partial_videos ?? "—", "var(--gold)")}
        {card("Untranslated", tr?.untranslated_videos ?? "—", "var(--ink-3)")}
        {card("Total cost", overview != null ? `$${overview.total_cost_usd.toFixed(4)}` : "—", "var(--ink)")}
        {card("Cache saved", overview != null ? `$${overview.cache_saved_usd.toFixed(4)}` : "—", "var(--green)")}
      </div>

      {/* Translation progress bar */}
      <div style={{ height: 10, background: "var(--warm-100)", borderRadius: 6, overflow: "hidden" }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${tr?.percent ?? 0}%` }}
          transition={{ duration: 0.5 }}
          style={{ height: "100%", background: "var(--gold)" }}
        />
      </div>

      {/* ── SECTION 2: Mission control ─────────────────────────────────────── */}
      <div style={{ background: "var(--white)", border: "1px solid var(--warm-200)", borderRadius: 12, padding: 16, boxShadow: "var(--shadow-card)" }}>
        <h2 className="font-display" style={{ fontSize: 18, color: "var(--ink)", letterSpacing: "-0.01em", marginBottom: 14 }}>Mission Control</h2>

        {!trRunning ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {/* Provider / model selector */}
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-3)" }}>Model</span>
              <select value={sel} onChange={(e) => setSel(e.target.value)}
                style={{ flex: "1 1 280px", minWidth: 220, maxWidth: 480, padding: "8px 10px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, color: "var(--ink)" }}>
                <option value="">Default (from config)</option>
                {opts.some((o) => o.provider === "youtube") && (
                  <option value="youtube::">YouTube auto-captions (free)</option>
                )}
                {opts.filter((o) => o.provider === "sarvam").map((o) => (
                  <option key={`sarvam-${o.model}`} value={`sarvam::${o.model ?? ""}`}>{o.label} — ₹0.002/char</option>
                ))}
                {opts.some((o) => o.provider === "openrouter" && o.free) && (
                  <optgroup label="OpenRouter — Free">
                    {opts.filter((o) => o.provider === "openrouter" && o.free).map((o) => (
                      <option key={o.model} value={`openrouter::${o.model ?? ""}`}>{o.label}</option>
                    ))}
                  </optgroup>
                )}
                {opts.some((o) => o.provider === "openrouter" && !o.free) && (
                  <optgroup label="OpenRouter — Paid ($/Mtok in·out)">
                    {opts.filter((o) => o.provider === "openrouter" && !o.free).map((o) => (
                      <option key={o.model} value={`openrouter::${o.model ?? ""}`}>{o.label} — ${o.prompt_per_mtok}·${o.completion_per_mtok}</option>
                    ))}
                  </optgroup>
                )}
              </select>
              <span style={{ fontSize: 12, fontFamily: "JetBrains Mono", color: estimate() === "Free" ? "var(--green)" : "var(--ink-2)" }}>{estimate()}</span>
              <button onClick={() => setShowAdv((s) => !s)}
                style={{ marginLeft: "auto", fontSize: 12, fontWeight: 600, background: "none", border: "none", color: "var(--gold)", cursor: "pointer" }}>
                {showAdv ? "Hide options" : "Advanced"}
              </button>
            </div>

            {showAdv && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "center" }}>
                <label style={{ fontSize: 12, color: "var(--ink-3)", display: "flex", alignItems: "center", gap: 6 }}>
                  Batch size
                  <input type="number" min={1} placeholder="1" value={batchSize}
                    onChange={(e) => setBatchSize(e.target.value === "" ? "" : Math.max(1, Number(e.target.value)))}
                    style={{ width: 70, padding: "6px 8px", borderRadius: 7, border: "1px solid var(--warm-200)", fontSize: 13 }} />
                </label>
                <label style={{ fontSize: 12, color: "var(--ink-3)", display: "flex", alignItems: "center", gap: 6 }}>
                  Videos in parallel
                  <input type="number" min={1} placeholder="2" value={vconc}
                    onChange={(e) => setVconc(e.target.value === "" ? "" : Math.max(1, Number(e.target.value)))}
                    style={{ width: 70, padding: "6px 8px", borderRadius: 7, border: "1px solid var(--warm-200)", fontSize: 13 }} />
                </label>
                <span style={{ fontSize: 11, color: "var(--ink-4)" }}>Batch size &gt;1 packs many segments per OpenRouter call (auto per-segment fallback if alignment fails).</span>
              </div>
            )}

            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
              <button onClick={() => startTranslate("pending")}
                style={{ padding: "10px 18px", borderRadius: 10, border: "none", background: "var(--gold)", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
                ⇄ Translate pending
              </button>
              <button onClick={() => startTranslate("all")}
                style={{ padding: "10px 18px", borderRadius: 10, border: "1px solid var(--warm-200)", background: "var(--white)", color: "var(--ink-2)", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
                ↻ Re-translate all
              </button>
              <span style={{ fontSize: 12, color: "var(--ink-3)" }}>
                {selOpt ? `Via ${selOpt.label}.` : "Via configured default."} Cache, retry &amp; glossary applied automatically.
              </span>
            </div>
          </div>
        ) : (
          /* Live telemetry */
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--gold)", animation: "pulse 1.4s infinite", flexShrink: 0 }} />
                <strong style={{ fontSize: 14, color: "var(--ink)" }}>Translating ({liveRun?.mode})</strong>
              </div>
              <span style={{ fontFamily: "JetBrains Mono", fontSize: 13, color: "var(--ink-2)" }}>
                {liveRun?.processed}/{liveRun?.total} videos · ✓{liveRun?.translated} segs{liveRun?.errors ? ` · ✗${liveRun.errors}` : ""}
              </span>
              {liveRun?.cost_usd != null && (
                <span style={{ fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--ink-2)" }}>${liveRun.cost_usd.toFixed(4)}</span>
              )}
              {etaStr && (
                <span style={{ fontSize: 12, color: "var(--ink-3)" }}>ETA {etaStr}</span>
              )}
              <button onClick={stopTranslate}
                style={{ padding: "8px 16px", borderRadius: 10, border: "1px solid var(--red-border)", background: "var(--red-light)", color: "var(--red)", fontSize: 13, fontWeight: 600, cursor: "pointer", marginLeft: "auto" }}>
                ■ Stop
              </button>
            </div>
            {liveRun?.current && (
              <div style={{ fontSize: 12, color: "var(--ink-3)" }}>
                current: <code style={{ fontFamily: "JetBrains Mono", background: "var(--warm-100)", padding: "1px 5px", borderRadius: 4 }}>{liveRun.current}</code>
              </div>
            )}
            {/* Live progress bar */}
            {liveRun && liveRun.total > 0 && (
              <div style={{ height: 6, background: "var(--warm-100)", borderRadius: 4, overflow: "hidden" }}>
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.round((liveRun.processed / liveRun.total) * 100)}%` }}
                  transition={{ duration: 0.4 }}
                  style={{ height: "100%", background: "var(--gold)" }}
                />
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── SECTION 3: Corpus table ────────────────────────────────────────── */}
      <div style={{ background: "var(--white)", border: "1px solid var(--warm-200)", borderRadius: 12, padding: 16, boxShadow: "var(--shadow-card)" }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, marginBottom: 14 }}>
          <h2 className="font-display" style={{ fontSize: 18, color: "var(--ink)", letterSpacing: "-0.01em", flex: "1 1 auto" }}>Corpus</h2>

          <select value={corpusFilter} onChange={(e) => { setCorpusFilter(e.target.value); setCorpusPage(1); }}
            style={{ padding: "7px 10px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, color: "var(--ink)" }}>
            {CORPUS_FILTERS.map((f) => <option key={f} value={f}>{f === "all" ? "All statuses" : (STATUS[f]?.label ?? f)}</option>)}
          </select>
          <input value={corpusQ} onChange={(e) => setCorpusQ(e.target.value)} placeholder="Search title or video ID…"
            style={{ flex: "1 1 200px", minWidth: 160, padding: "7px 10px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, outline: "none" }} />
          {uni && <span style={{ fontSize: 12, color: "var(--ink-3)", whiteSpace: "nowrap" }}>{uni.total.toLocaleString()} results · page {uni.page}/{uni.total_pages}</span>}
        </div>

        <div className="scroll-x">
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, minWidth: 700 }}>
            <thead>
              <tr>
                {["Title", "Video ID", "Status", "Segs", "Translated", "Actions"].map((h) => (
                  <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontSize: 11, fontWeight: 600, color: "var(--ink-3)", letterSpacing: "0.05em", textTransform: "uppercase", background: "var(--cream)", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {!uni && <tr><td colSpan={6} style={{ padding: "48px 0", textAlign: "center", color: "var(--ink-3)" }}>Loading…</td></tr>}
              {uni?.items.map((r, i) => {
                const s = STATUS[r.status] ?? STATUS.not_attempted;
                return (
                  <tr key={r.youtube_id} style={{ borderTop: i > 0 ? "1px solid var(--warm-100)" : "none" }}>
                    <td style={{ padding: "11px 14px", maxWidth: 320 }}>
                      <p style={{ fontWeight: 500, color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 320 }}>{r.title || "—"}</p>
                      {r.error_msg && <p style={{ fontSize: 11, color: "var(--red)", marginTop: 3, lineHeight: 1.4 }}>{r.error_msg.slice(0, 100)}</p>}
                    </td>
                    <td style={{ padding: "11px 14px", fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--ink-3)", whiteSpace: "nowrap" }}>
                      <a href={`https://youtu.be/${r.youtube_id}`} target="_blank" rel="noreferrer" style={{ color: "var(--ink-3)", textDecoration: "none" }}>{r.youtube_id}</a>
                    </td>
                    <td style={{ padding: "11px 14px" }}>
                      <span style={{ fontSize: 11, fontWeight: 600, padding: "3px 8px", borderRadius: 20, background: s.bg, color: s.color, whiteSpace: "nowrap" }}>{s.label}</span>
                    </td>
                    <td style={{ padding: "11px 14px", fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--ink-2)" }}>{r.segment_count || "—"}</td>
                    <td style={{ padding: "11px 14px" }}>
                      <TrCell done={r.translated_count} total={r.segment_count} />
                    </td>
                    <td style={{ padding: "11px 14px", whiteSpace: "nowrap" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Link href={`/editor/${r.youtube_id}`} style={{ fontSize: 12, fontWeight: 600, color: "var(--gold)", textDecoration: "none" }}>Edit →</Link>
                        <button onClick={() => translateOne(r.youtube_id)} disabled={trRunning}
                          style={{ fontSize: 11, fontWeight: 600, padding: "3px 8px", borderRadius: 6, border: "1px solid var(--warm-200)", background: "var(--cream)", color: "var(--ink-2)", cursor: trRunning ? "not-allowed" : "pointer", opacity: trRunning ? 0.5 : 1 }}>
                          ⇄
                        </button>
                        <button onClick={() => { setRemoveId(r.youtube_id); setRemoveTitle(r.title); }}
                          title="Move to Recycle Bin"
                          style={{ fontSize: 12, fontWeight: 600, color: "var(--red)", background: "none", border: "none", cursor: "pointer" }}>
                          🗑 Remove
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {uni?.items.length === 0 && <tr><td colSpan={6} style={{ padding: "48px 0", textAlign: "center", color: "var(--ink-3)" }}>No matching videos.</td></tr>}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {uni && uni.total_pages > 1 && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 14, marginTop: 16 }}>
            <button onClick={() => setCorpusPage((p) => Math.max(1, p - 1))} disabled={corpusPage <= 1}
              style={{ padding: "7px 14px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, cursor: corpusPage <= 1 ? "not-allowed" : "pointer", opacity: corpusPage <= 1 ? 0.5 : 1 }}>← Prev</button>
            <span style={{ fontSize: 13, color: "var(--ink-3)", fontFamily: "JetBrains Mono" }}>{corpusPage} / {uni.total_pages}</span>
            <button onClick={() => setCorpusPage((p) => Math.min(uni.total_pages, p + 1))} disabled={corpusPage >= uni.total_pages}
              style={{ padding: "7px 14px", borderRadius: 8, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, cursor: corpusPage >= uni.total_pages ? "not-allowed" : "pointer", opacity: corpusPage >= uni.total_pages ? 0.5 : 1 }}>Next →</button>
          </div>
        )}
      </div>

      {/* ── SECTION 4: Cost breakdown ──────────────────────────────────────── */}
      <div style={{ background: "var(--white)", border: "1px solid var(--warm-200)", borderRadius: 12, padding: 16, boxShadow: "var(--shadow-card)" }}>
        <h2 className="font-display" style={{ fontSize: 18, color: "var(--ink)", letterSpacing: "-0.01em", marginBottom: 14 }}>Cost &amp; Budget</h2>

        {!overview || overview.by_model.length === 0 ? (
          <p style={{ fontSize: 13, color: "var(--ink-3)" }}>No cost data yet — run a translation to see spend.</p>
        ) : (
          <>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 14 }}>
              <div style={{ background: "var(--green-light)", border: "1px solid var(--green-border)", borderRadius: 10, padding: "10px 16px" }}>
                <p style={{ fontSize: 11, fontWeight: 600, color: "var(--green)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Total Spend</p>
                <p style={{ fontSize: 22, fontWeight: 700, color: "var(--ink)", fontFamily: "JetBrains Mono", marginTop: 2 }}>${overview.total_cost_usd.toFixed(4)}</p>
              </div>
              <div style={{ background: "var(--green-light)", border: "1px solid var(--green-border)", borderRadius: 10, padding: "10px 16px" }}>
                <p style={{ fontSize: 11, fontWeight: 600, color: "var(--green)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Cache Saved</p>
                <p style={{ fontSize: 22, fontWeight: 700, color: "var(--green)", fontFamily: "JetBrains Mono", marginTop: 2 }}>${overview.cache_saved_usd.toFixed(4)}</p>
              </div>
              <div style={{ background: "var(--cream)", border: "1px solid var(--warm-200)", borderRadius: 10, padding: "10px 16px" }}>
                <p style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Segs Translated</p>
                <p style={{ fontSize: 22, fontWeight: 700, color: "var(--ink)", fontFamily: "JetBrains Mono", marginTop: 2 }}>{overview.total_translated_segs.toLocaleString()}</p>
              </div>
            </div>

            <div className="scroll-x">
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr>
                    {["Provider", "Model", "Segments", "Cost", "Cost / 1k segs"].map((h) => (
                      <th key={h} style={{ padding: "8px 12px", textAlign: "left", fontSize: 11, fontWeight: 600, color: "var(--ink-3)", letterSpacing: "0.05em", textTransform: "uppercase", background: "var(--cream)", whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {overview.by_model.map((row, i) => (
                    <tr key={i} style={{ borderTop: i > 0 ? "1px solid var(--warm-100)" : "none" }}>
                      <td style={{ padding: "9px 12px", fontWeight: 500, color: "var(--ink)" }}>{row.provider}</td>
                      <td style={{ padding: "9px 12px", fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--ink-3)" }}>{row.model ?? "—"}</td>
                      <td style={{ padding: "9px 12px", fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--ink-2)" }}>{row.segments.toLocaleString()}</td>
                      <td style={{ padding: "9px 12px", fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--ink)" }}>${row.cost_usd.toFixed(4)}</td>
                      <td style={{ padding: "9px 12px", fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--ink-3)" }}>
                        {row.segments > 0 ? `$${(row.cost_usd / row.segments * 1000).toFixed(4)}` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      {/* ── SECTION 5: Quality flags ───────────────────────────────────────── */}
      <div style={{ background: "var(--white)", border: "1px solid var(--warm-200)", borderRadius: 12, padding: 16, boxShadow: "var(--shadow-card)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14, gap: 8 }}>
          <h2 className="font-display" style={{ fontSize: 18, color: "var(--ink)", letterSpacing: "-0.01em" }}>Quality Flags</h2>
          {flagsData && <span style={{ fontSize: 12, color: "var(--ink-3)", fontFamily: "JetBrains Mono" }}>{flagsData.total} total</span>}
        </div>

        {!flagsData || flagsData.flags.length === 0 ? (
          <p style={{ fontSize: 13, color: "var(--green)", fontWeight: 500 }}>No quality issues found ✓</p>
        ) : (
          <div className="scroll-x">
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  {["Issue", "Telugu original", "English translation", "Score", ""].map((h) => (
                    <th key={h} style={{ padding: "8px 12px", textAlign: "left", fontSize: 11, fontWeight: 600, color: "var(--ink-3)", letterSpacing: "0.05em", textTransform: "uppercase", background: "var(--cream)", whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {flagsData.flags.slice(0, 20).map((f, i) => {
                  const badge = FLAG_BADGE[f.issue] ?? { color: "var(--gray-500)", bg: "var(--gray-100)" };
                  return (
                    <tr key={f.segment_id} style={{ borderTop: i > 0 ? "1px solid var(--warm-100)" : "none" }}>
                      <td style={{ padding: "9px 12px", whiteSpace: "nowrap" }}>
                        <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 20, background: badge.bg, color: badge.color }}>{f.issue}</span>
                      </td>
                      <td style={{ padding: "9px 12px", maxWidth: 240, color: "var(--ink-2)" }}>
                        <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 240, fontSize: 12 }}>
                          {f.te_original.length > 80 ? f.te_original.slice(0, 80) + "…" : f.te_original}
                        </span>
                      </td>
                      <td style={{ padding: "9px 12px", maxWidth: 240, color: "var(--ink-3)" }}>
                        <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 240, fontSize: 12 }}>
                          {f.en_final ? (f.en_final.length > 80 ? f.en_final.slice(0, 80) + "…" : f.en_final) : <em>—</em>}
                        </span>
                      </td>
                      <td style={{ padding: "9px 12px", fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--ink-3)", whiteSpace: "nowrap" }}>
                        {f.quality_score != null ? f.quality_score.toFixed(2) : "—"}
                      </td>
                      <td style={{ padding: "9px 12px", whiteSpace: "nowrap" }}>
                        <Link href={`/editor/${f.youtube_id}`} style={{ fontSize: 12, fontWeight: 600, color: "var(--gold)", textDecoration: "none" }}>Edit →</Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── SECTION 6: Provider intelligence ──────────────────────────────── */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
        {/* Left: Credits */}
        <div style={{ flex: "1 1 280px", minWidth: 260, background: "var(--white)", border: "1px solid var(--warm-200)", borderRadius: 12, padding: 16, boxShadow: "var(--shadow-card)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <h2 className="font-display" style={{ fontSize: 18, color: "var(--ink)", letterSpacing: "-0.01em" }}>Credits</h2>
            <button onClick={() => { mutateCredits(); mutateOverview(); mutateFlags(); }}
              style={{ fontSize: 12, background: "none", border: "1px solid var(--warm-200)", borderRadius: 7, padding: "4px 10px", cursor: "pointer", color: "var(--ink-3)" }}>
              ↻ Refresh
            </button>
          </div>

          {credits?.openrouter != null && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>OpenRouter</span>
                {credits.openrouter.is_free_tier && (
                  <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 20, background: "var(--green-light)", color: "var(--green)", letterSpacing: "0.04em" }}>FREE TIER</span>
                )}
              </div>
              {credits.openrouter.error ? (
                <p style={{ fontSize: 12, color: "var(--red)" }}>{credits.openrouter.error}</p>
              ) : (
                <>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--ink-3)", marginBottom: 4 }}>
                    <span>Usage: ${credits.openrouter.usage.toFixed(4)}</span>
                    {credits.openrouter.remaining != null && <span>Remaining: ${credits.openrouter.remaining.toFixed(2)}</span>}
                  </div>
                  {credits.openrouter.limit != null && credits.openrouter.limit > 0 && (
                    <div style={{ height: 6, background: "var(--warm-100)", borderRadius: 4, overflow: "hidden" }}>
                      <div style={{ height: "100%", width: `${Math.min(100, (credits.openrouter.usage / credits.openrouter.limit) * 100).toFixed(1)}%`, background: "var(--gold)" }} />
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {credits?.sarvam && (
            <div>
              <span style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)", display: "block", marginBottom: 4 }}>Sarvam</span>
              <p style={{ fontSize: 12, color: "var(--ink-3)" }}>{credits.sarvam.note}</p>
            </div>
          )}

          {!credits && <p style={{ fontSize: 13, color: "var(--ink-3)" }}>Loading credits…</p>}
        </div>

        {/* Right: Info card */}
        <div style={{ flex: "1 1 280px", minWidth: 260, background: "var(--cream)", border: "1px solid var(--warm-200)", borderRadius: 12, padding: 16, boxShadow: "var(--shadow-card)" }}>
          <h2 className="font-display" style={{ fontSize: 16, color: "var(--ink)", letterSpacing: "-0.01em", marginBottom: 10 }}>How it works</h2>
          <ul style={{ fontSize: 12, color: "var(--ink-3)", lineHeight: 1.8, paddingLeft: 16, display: "flex", flexDirection: "column", gap: 4 }}>
            <li>Batch translate packs multiple segments per API call to reduce costs.</li>
            <li>Cache deduplicates identical Telugu source segments — pay once per unique phrase.</li>
            <li>Glossary terms (Biblical names, scripture refs) are protected and passed through unchanged.</li>
            <li>If per-segment alignment fails, the engine falls back to single-segment mode automatically.</li>
            <li>YouTube auto-captions are free but quality may vary — use for initial coverage, then refine.</li>
            <li>The queue pauses automatically when YouTube quota approaches 9,500 units/day.</li>
          </ul>
        </div>
      </div>

      <RemoveDialog
        open={!!removeId}
        youtubeId={removeId}
        title={removeTitle}
        scope="translation"
        onClose={() => { setRemoveId(null); setRemoveTitle(null); }}
        onRemoved={() => { mutateUni(); mutateOverview(); }}
      />

    </div>
  );
}
