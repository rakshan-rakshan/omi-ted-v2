"use client";
import { useState, useCallback, useEffect, useRef } from "react";
import { useParams } from "next/navigation";
import useSWR from "swr";
import Link from "next/link";
import axios from "axios";
import { motion, AnimatePresence } from "motion/react";
import YouTubePlayer, { YouTubePlayerHandle } from "@/components/YouTubePlayer";
import SegmentMicInput from "@/components/SegmentMicInput";

// ── Types ─────────────────────────────────────────────────────────────────

export interface Segment {
  id: number; segment_index: number; start_time: number; duration: number;
  te_original: string; en_auto: string | null; en_human: string | null;
  en_final: string | null; content_type: string; is_reviewed: boolean; quality_score: number | null;
}
interface SegmentsPage {
  total: number; page: number; page_size: number; total_pages: number; items: Segment[];
}
interface TranslateResult { translated: number; skipped: number; errors: number; message: string; }

type Provider = "youtube" | "sarvam" | "openrouter";
type EditorMode = "fulltext" | "sentences" | "finetune";

const PRESETS = [
  { id: "google/gemma-3-27b-it",                   label: "Gemma 3 · 27B" },
  { id: "google/gemma-3-12b-it",                   label: "Gemma 3 · 12B" },
  { id: "anthropic/claude-3-haiku",                label: "Claude 3 Haiku" },
  { id: "meta-llama/llama-3.3-70b-instruct",       label: "Llama 3.3 · 70B" },
  { id: "custom",                                  label: "Custom model…" },
];

const fetcher = (u: string) => axios.get(u).then(r => r.data);
const PAGE_SIZE = 50;

function fmtTime(s: number) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
  if (h > 0) return `${h}:${m.toString().padStart(2,"0")}:${sec.toString().padStart(2,"0")}`;
  return `${m}:${sec.toString().padStart(2,"0")}`;
}

// ── Mode A: Full Text split-screen ────────────────────────────────────────

function FullTextMode({ videoId, seekTo }: { videoId: string; seekTo: (seconds: number) => void }) {
  const { data, isLoading } = useSWR<SegmentsPage>(
    `/api/v1/videos/${videoId}/segments?page=1&page_size=9999`, fetcher
  );
  const items = data?.items ?? [];

  if (isLoading) return (
    <div style={{ padding: "60px 0", textAlign: "center", color: "var(--gray-400)", fontSize: 13 }}>
      Loading full transcript…
    </div>
  );

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0, height: "calc(100vh - 140px)", border: "1px solid var(--gray-200)", borderRadius: 12, overflow: "hidden" }}>
      {/* Left: Telugu */}
      <div style={{ padding: "24px 28px", overflowY: "auto", borderRight: "1px solid var(--gray-200)", background: "var(--white)" }}>
        <p style={{ fontSize: 11, fontWeight: 600, color: "var(--rose)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 16 }}>
          తెలుగు — Telugu Source
        </p>
        <div style={{ fontFamily: "'Noto Sans Telugu', sans-serif", fontSize: 15, lineHeight: 2, color: "var(--gray-900)" }}>
          {items.map((seg, i) => (
            <span key={seg.id}>
              <button onClick={() => seekTo(seg.start_time)}
                style={{ fontSize: 10, color: "var(--gray-300)", fontFamily: "JetBrains Mono", textDecoration: "none", marginRight: 4, verticalAlign: "middle", background: "none", border: "none", cursor: "pointer", padding: 0 }}>
                {fmtTime(seg.start_time)}
              </button>
              {seg.te_original}
              {i < items.length - 1 ? " " : ""}
            </span>
          ))}
        </div>
      </div>
      {/* Right: English */}
      <div style={{ padding: "24px 28px", overflowY: "auto", background: "var(--gray-50)" }}>
        <p style={{ fontSize: 11, fontWeight: 600, color: "var(--amber)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 16 }}>
          English — Auto Translation
        </p>
        <div style={{ fontSize: 14, lineHeight: 2, color: "var(--gray-700)" }}>
          {items.map((seg, i) => (
            <span key={seg.id}>
              {seg.en_human || seg.en_auto || <em style={{ color: "var(--gray-300)" }}>[no translation]</em>}
              {i < items.length - 1 ? " " : ""}
            </span>
          ))}
        </div>
        {items.every(s => !s.en_auto && !s.en_human) && (
          <p style={{ fontSize: 13, color: "var(--gray-400)", marginTop: 32 }}>
            No auto-translations yet. Use the Auto-translate button to generate them.
          </p>
        )}
      </div>
    </div>
  );
}

// ── Mode B: Sentence-parallel table ──────────────────────────────────────

function SentenceRow({ seg, youtubeId, onUpdate, seekTo, translatingSegId, onTranslate }: {
  seg: Segment; youtubeId: string; onUpdate: (id: number, u: Partial<Segment>) => void;
  seekTo: (seconds: number) => void; translatingSegId: number | null;
  onTranslate: (segId: number) => void;
}) {
  const [val, setVal] = useState(seg.en_human ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { setVal(seg.en_human ?? ""); }, [seg.en_human]);

  async function save() {
    const trimmed = val.trim();
    if (trimmed === (seg.en_human ?? "")) return;
    setSaving(true);
    try {
      const { data } = await axios.patch(`/api/v1/segments/${seg.id}`, { en_human: trimmed, is_reviewed: trimmed.length > 0 });
      onUpdate(seg.id, data);
      setSaved(true); setTimeout(() => setSaved(false), 1800);
    } catch (e) { console.error(e); }
    finally { setSaving(false); }
  }

  const isDone = !!seg.en_human;

  return (
    <tr style={{ borderBottom: "1px solid var(--gray-100)", background: isDone ? "rgba(16,185,129,0.02)" : "var(--white)" }}>
      {/* Timestamp */}
      <td style={{ padding: "12px 14px", verticalAlign: "top", whiteSpace: "nowrap", width: 70 }}>
        <button onClick={() => seekTo(seg.start_time)}
          style={{ fontSize: 11, fontFamily: "JetBrains Mono", color: "var(--rose)", background: "none", border: "none", cursor: "pointer", fontWeight: 600, padding: 0, textDecoration: "none" }}>
          {fmtTime(seg.start_time)}
        </button>
      </td>
      {/* Actions */}
      <td style={{ padding: "12px 6px", verticalAlign: "top", whiteSpace: "nowrap", width: 60 }}>
        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          <SegmentMicInput onResult={text => {
            axios.patch(`/api/v1/segments/${seg.id}`, { en_human: text.trim(), is_reviewed: true })
              .then(({ data: updated }) => onUpdate(seg.id, updated));
          }} language="te-IN" />
          <button
            onClick={() => onTranslate(seg.id)}
            title="Translate this segment"
            disabled={translatingSegId === seg.id}
            style={{
              width: 28, height: 28, borderRadius: 6, border: "1px solid var(--gray-200)",
              background: "var(--white)", color: "var(--gray-500)",
              cursor: "pointer", fontSize: 12, display: "flex", alignItems: "center", justifyContent: "center",
              opacity: translatingSegId === seg.id ? 0.5 : 1,
            }}
          >
            {translatingSegId === seg.id ? "…" : "⚡"}
          </button>
        </div>
      </td>
      {/* Telugu */}
      <td style={{ padding: "12px 14px", verticalAlign: "top", width: "40%" }}>
        <p style={{ fontFamily: "'Noto Sans Telugu', sans-serif", fontSize: 14, lineHeight: 1.8, color: "var(--gray-900)", margin: 0 }}>
          {seg.te_original}
        </p>
      </td>
      {/* English editable */}
      <td style={{ padding: "10px 14px", verticalAlign: "top" }}>
        <div style={{ position: "relative" }}>
          <textarea ref={ref} value={val}
            onChange={e => setVal(e.target.value)}
            onBlur={save}
            onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); ref.current?.blur(); } }}
            rows={Math.max(2, Math.ceil(seg.te_original.length / 60))}
            placeholder={seg.en_auto ? seg.en_auto : "Type translation…"}
            style={{
              width: "100%", padding: "8px 10px", borderRadius: 8, resize: "vertical",
              fontSize: 13, lineHeight: 1.6, fontFamily: "DM Sans, sans-serif",
              border: `1px solid ${isDone ? "var(--green-border)" : "var(--gray-200)"}`,
              background: isDone ? "rgba(16,185,129,0.03)" : "var(--gray-50)",
              color: "var(--gray-900)", outline: "none", transition: "border-color 0.15s",
            }}
            onFocus={e => { e.target.style.borderColor = "var(--rose)"; e.target.style.boxShadow = "0 0 0 3px rgba(244,63,94,0.08)"; e.target.style.background = "var(--white)"; }}
            onBlurCapture={e => { e.target.style.borderColor = isDone ? "var(--green-border)" : "var(--gray-200)"; e.target.style.boxShadow = "none"; e.target.style.background = isDone ? "rgba(16,185,129,0.03)" : "var(--gray-50)"; }}
          />
          {/* Auto hint shown below if not yet edited */}
          {!isDone && seg.en_auto && (
            <p style={{ fontSize: 11, color: "var(--gray-400)", margin: "4px 2px 0", fontStyle: "italic", lineHeight: 1.5 }}>
              Auto: {seg.en_auto}
            </p>
          )}
          <div style={{ position: "absolute", top: 6, right: 8, fontSize: 11, pointerEvents: "none" }}>
            {saving && <span style={{ color: "var(--gray-400)" }}>…</span>}
            {saved && <motion.span style={{ color: "var(--green)" }} initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}>✓</motion.span>}
          </div>
        </div>
      </td>
    </tr>
  );
}

function SentencesMode({ videoId, page, setPage, data, isLoading, error, handleUpdate, seekTo, translatingSegId, onTranslate }: {
  videoId: string; page: number; setPage: (fn: (p: number) => number) => void;
  data: SegmentsPage | undefined; isLoading: boolean; error: unknown;
  handleUpdate: (id: number, u: Partial<Segment>) => void;
  seekTo: (seconds: number) => void; translatingSegId: number | null;
  onTranslate: (segId: number) => void;
}) {
  if (isLoading) return <div style={{ padding: "60px 0", textAlign: "center", color: "var(--gray-400)", fontSize: 13 }}>Loading segments…</div>;
  if (error) return <div style={{ padding: "40px 0", textAlign: "center", color: "var(--red)", fontSize: 13 }}>Failed to load — is the backend running?</div>;

  return (
    <div style={{ background: "var(--white)", border: "1px solid var(--gray-200)", borderRadius: 12, overflow: "hidden" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "var(--gray-50)", borderBottom: "1px solid var(--gray-200)" }}>
            <th style={{ padding: "10px 14px", fontSize: 11, fontWeight: 600, color: "var(--gray-400)", textAlign: "left", textTransform: "uppercase", letterSpacing: "0.06em", width: 70 }}>Time</th>
            <th style={{ padding: "10px 14px", fontSize: 11, fontWeight: 600, color: "var(--gray-400)", textAlign: "left", textTransform: "uppercase", letterSpacing: "0.06em", width: 60 }}>Actions</th>
            <th style={{ padding: "10px 14px", fontSize: 11, fontWeight: 600, color: "var(--gray-400)", textAlign: "left", textTransform: "uppercase", letterSpacing: "0.06em", width: "40%" }}>తెలుగు</th>
            <th style={{ padding: "10px 14px", fontSize: 11, fontWeight: 600, color: "var(--gray-400)", textAlign: "left", textTransform: "uppercase", letterSpacing: "0.06em" }}>English (your translation)</th>
          </tr>
        </thead>
        <tbody>
          {data?.items.map(seg => (
            <SentenceRow key={seg.id} seg={seg} youtubeId={videoId} onUpdate={handleUpdate}
              seekTo={seekTo} translatingSegId={translatingSegId}
              onTranslate={onTranslate} />
          ))}
        </tbody>
      </table>
      {data && data.total_pages > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, padding: "14px 20px", borderTop: "1px solid var(--gray-100)" }}>
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
            style={{ padding: "6px 14px", borderRadius: 8, border: "1px solid var(--gray-200)", background: "var(--white)", color: "var(--gray-500)", fontSize: 12, cursor: "pointer" }}>
            ← Prev
          </button>
          <span style={{ fontSize: 12, color: "var(--gray-400)", fontFamily: "JetBrains Mono" }}>{page} / {data.total_pages}</span>
          <button onClick={() => setPage(p => Math.min(data.total_pages, p + 1))} disabled={page === data.total_pages}
            style={{ padding: "6px 14px", borderRadius: 8, border: "1px solid var(--gray-200)", background: "var(--white)", color: "var(--gray-500)", fontSize: 12, cursor: "pointer" }}>
            Next →
          </button>
        </div>
      )}
    </div>
  );
}

// ── Mode C: Fine-tune cards ──────────────────────────────────────────────

function FineTuneCard({ seg, youtubeId, onUpdate, seekTo, translatingSegId, onTranslate }: {
  seg: Segment; youtubeId: string; onUpdate: (id: number, u: Partial<Segment>) => void;
  seekTo: (seconds: number) => void; translatingSegId: number | null;
  onTranslate: (segId: number) => void;
}) {
  const [val, setVal] = useState(seg.en_human ?? seg.en_auto ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { setVal(seg.en_human ?? seg.en_auto ?? ""); }, [seg.en_human, seg.en_auto]);

  async function save() {
    const trimmed = val.trim();
    if (trimmed === (seg.en_human ?? "")) return;
    setSaving(true);
    try {
      const { data } = await axios.patch(`/api/v1/segments/${seg.id}`, { en_human: trimmed, is_reviewed: trimmed.length > 0 });
      onUpdate(seg.id, data);
      setSaved(true); setTimeout(() => setSaved(false), 1800);
    } catch (e) { console.error(e); }
    finally { setSaving(false); }
  }

  return (
    <motion.div layout
      style={{
        background: seg.is_reviewed ? "rgba(16,185,129,0.03)" : "var(--white)",
        border: `1px solid ${seg.is_reviewed ? "var(--green-border)" : "var(--gray-200)"}`,
        borderRadius: 12, padding: "16px 20px", display: "flex", flexDirection: "column", gap: 10,
      }}
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 380, damping: 28 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <button onClick={() => seekTo(seg.start_time)}
          style={{ fontSize: 12, fontFamily: "JetBrains Mono", fontWeight: 600, color: "var(--rose)", textDecoration: "none", background: "none", border: "none", cursor: "pointer", padding: 0 }}>
          {fmtTime(seg.start_time)}
        </button>
        <span style={{ fontSize: 10, color: "var(--gray-400)" }}>·</span>
        <span style={{ fontSize: 10, color: "var(--gray-400)" }}>{seg.duration.toFixed(1)}s</span>
        <SegmentMicInput onResult={text => {
          axios.patch(`/api/v1/segments/${seg.id}`, { en_human: text.trim(), is_reviewed: true })
            .then(({ data: updated }) => onUpdate(seg.id, updated));
        }} language="te-IN" />
        <button
          onClick={() => onTranslate(seg.id)}
          title="Translate this segment"
          disabled={translatingSegId === seg.id}
          style={{
            width: 28, height: 28, borderRadius: 6, border: "1px solid var(--gray-200)",
            background: "var(--white)", color: "var(--gray-500)",
            cursor: "pointer", fontSize: 12, display: "flex", alignItems: "center", justifyContent: "center",
            opacity: translatingSegId === seg.id ? 0.5 : 1,
          }}
        >
          {translatingSegId === seg.id ? "…" : "⚡"}
        </button>
        {seg.is_reviewed && (
          <span style={{ fontSize: 10, fontWeight: 600, color: "var(--green)", background: "var(--green-light)", border: "1px solid var(--green-border)", padding: "1px 6px", borderRadius: 10, marginLeft: "auto" }}>
            ✓ done
          </span>
        )}
      </div>
      <p style={{ fontSize: 14, lineHeight: 1.7, color: "var(--gray-900)", fontFamily: "'Noto Sans Telugu', sans-serif", margin: 0 }}>
        {seg.te_original}
      </p>
      {/* In fine-tune mode, auto-translation pre-fills the textarea for editing */}
      <div style={{ position: "relative" }}>
        <textarea ref={ref} value={val}
          onChange={e => setVal(e.target.value)}
          onBlur={save}
          onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); ref.current?.blur(); } }}
          rows={3}
          placeholder={seg.en_auto ? seg.en_auto : "Edit the English translation…"}
          style={{
            width: "100%", padding: "10px 12px", borderRadius: 8, resize: "vertical",
            fontSize: 13, lineHeight: 1.6, fontFamily: "DM Sans, sans-serif",
            border: "1px solid var(--gray-200)", background: "var(--gray-50)",
            color: "var(--gray-900)", outline: "none", transition: "border-color 0.15s",
          }}
          onFocus={e => { e.target.style.borderColor = "var(--rose)"; e.target.style.boxShadow = "0 0 0 3px rgba(244,63,94,0.08)"; e.target.style.background = "var(--white)"; }}
          onBlurCapture={e => { e.target.style.borderColor = "var(--gray-200)"; e.target.style.boxShadow = "none"; e.target.style.background = "var(--gray-50)"; }}
        />
        {seg.en_auto && (!seg.en_human || seg.en_human !== seg.en_auto) && (
          <p style={{ fontSize: 10, color: "var(--gray-400)", margin: "4px 2px 0", fontStyle: "italic" }}>
            {seg.en_human ? "Original auto: " : "Auto: "}{seg.en_auto}
          </p>
        )}
        <div style={{ position: "absolute", top: 8, right: 10, fontSize: 11, pointerEvents: "none" }}>
          {saving && <span style={{ color: "var(--gray-400)" }}>saving…</span>}
          {saved && <motion.span style={{ color: "var(--green)" }} initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}>✓</motion.span>}
        </div>
      </div>
    </motion.div>
  );
}

function FineTuneMode({ videoId, page, setPage, data, isLoading, error, handleUpdate, seekTo, translatingSegId, onTranslate }: {
  videoId: string; page: number; setPage: (fn: (p: number) => number) => void;
  data: SegmentsPage | undefined; isLoading: boolean; error: unknown;
  handleUpdate: (id: number, u: Partial<Segment>) => void;
  seekTo: (seconds: number) => void; translatingSegId: number | null;
  onTranslate: (segId: number) => void;
}) {
  if (isLoading) return <div style={{ padding: "60px 0", textAlign: "center", color: "var(--gray-400)", fontSize: 13 }}>Loading…</div>;
  if (error) return <div style={{ padding: "40px 0", textAlign: "center", color: "var(--red)", fontSize: 13 }}>Failed to load — is the backend running?</div>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {data?.items.map(seg => (
        <FineTuneCard key={seg.id} seg={seg} youtubeId={videoId} onUpdate={handleUpdate}
          seekTo={seekTo} translatingSegId={translatingSegId}
          onTranslate={onTranslate} />
      ))}
      {data && data.total_pages > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, paddingTop: 8 }}>
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
            style={{ padding: "7px 18px", borderRadius: 8, border: "1px solid var(--gray-200)", background: "var(--white)", color: "var(--gray-500)", fontSize: 12, cursor: "pointer" }}>
            ← Prev
          </button>
          <span style={{ fontSize: 12, color: "var(--gray-400)", fontFamily: "JetBrains Mono" }}>{page} / {data.total_pages}</span>
          <button onClick={() => setPage(p => Math.min(data.total_pages, p + 1))} disabled={page === data.total_pages}
            style={{ padding: "7px 18px", borderRadius: 8, border: "1px solid var(--gray-200)", background: "var(--white)", color: "var(--gray-500)", fontSize: 12, cursor: "pointer" }}>
            Next →
          </button>
        </div>
      )}
    </div>
  );
}

// ── Main Editor Page ──────────────────────────────────────────────────────

const MODE_TABS: { id: EditorMode; label: string; desc: string }[] = [
  { id: "fulltext",  label: "Full Text",     desc: "Read the whole sermon — Telugu left, English right" },
  { id: "sentences", label: "Sentence View", desc: "Edit line by line with timestamps" },
  { id: "finetune",  label: "Fine-tune",     desc: "Card-by-card editing for training data" },
];

export default function EditorPage() {
  const { videoId } = useParams() as { videoId: string };
  const [mode, setMode] = useState<EditorMode>("sentences");
  const [page, setPage] = useState(1);
  const [provider, setProvider] = useState<Provider>("sarvam");
  const [modelPreset, setModelPreset] = useState(PRESETS[0].id);
  const [customModel, setCustomModel] = useState("");
  const [translating, setTranslating] = useState(false);
  const [txResult, setTxResult] = useState<TranslateResult | null>(null);
  const [txError, setTxError] = useState<string | null>(null);
  const [exportFormat, setExportFormat] = useState<"raw" | "alpaca" | "openai">("raw");
  const [markingAll, setMarkingAll] = useState(false);
  const [showAutoPanel, setShowAutoPanel] = useState(false);
  const playerRef = useRef<YouTubePlayerHandle>(null);
  const [translatingSegId, setTranslatingSegId] = useState<number | null>(null);

  useEffect(() => {
    const p = localStorage.getItem("omi_provider") as Provider | null;
    const m = localStorage.getItem("omi_model");
    if (p) setProvider(p);
    if (m) {
      const pr = PRESETS.find(x => x.id === m);
      if (pr) setModelPreset(m);
      else { setModelPreset("custom"); setCustomModel(m); }
    }
  }, []);

  const activeModel = modelPreset === "custom" ? customModel : modelPreset;

  const { data, error, isLoading, mutate } = useSWR<SegmentsPage>(
    `/api/v1/videos/${videoId}/segments?page=${page}&page_size=${PAGE_SIZE}`, fetcher
  );

  const handleUpdate = useCallback((id: number, updated: Partial<Segment>) => {
    mutate(prev => prev ? { ...prev, items: prev.items.map(s => s.id === id ? { ...s, ...updated } : s) } : prev, false);
  }, [mutate]);

  const done      = data?.items.filter(s => s.en_human && s.en_human.trim()).length ?? 0;
  const remaining = (data?.items.length ?? 0) - done;
  const total     = data?.items.length ?? 0;
  const allDone   = total > 0 && remaining === 0;

  async function autoTranslate() {
    setTranslating(true); setTxResult(null); setTxError(null);
    try {
      const { data: r } = await axios.post("/api/v1/batch/translate", {
        youtube_id: videoId, provider, model: activeModel, force: false, concurrency: 5,
      });
      setTxResult(r); mutate();
    } catch (err: unknown) {
      const m = axios.isAxiosError(err) ? err.response?.data?.detail ?? err.message : String(err);
      setTxError(typeof m === "string" ? m : JSON.stringify(m));
    } finally { setTranslating(false); }
  }

  async function markPageReviewed() {
    if (!data) return;
    const un = data.items.filter(s => !s.is_reviewed);
    if (!un.length) return;
    setMarkingAll(true);
    try {
      await Promise.all(un.map(s =>
        axios.patch(`/api/v1/segments/${s.id}`, { is_reviewed: true }).then(({ data: u }) => handleUpdate(s.id, u))
      ));
    }     finally { setMarkingAll(false); }
  }

  const handleSeekTo = useCallback((seconds: number) => {
    playerRef.current?.seekTo(seconds);
  }, []);

  async function translateSegment(segId: number) {
    setTranslatingSegId(segId);
    setTxResult(null); setTxError(null);
    try {
      const { data: r } = await axios.post("/api/v1/batch/translate", {
        youtube_id: videoId,
        provider,
        model: activeModel,
        segment_ids: [segId],
        force: true,
        concurrency: 1,
      });
      setTxResult(r); mutate();
    } catch (err) {
      const m = axios.isAxiosError(err) ? err.response?.data?.detail ?? err.message : String(err);
      setTxError(typeof m === "string" ? m : JSON.stringify(m));
    } finally {
      setTranslatingSegId(null);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>

      {/* ── Top bar: back link + mode tabs + compact auto-translate ── */}
      <div style={{
        display: "flex", alignItems: "center", gap: 16,
        paddingBottom: 16, borderBottom: "1px solid var(--gray-100)", marginBottom: 20,
        flexWrap: "wrap",
      }}>
        <Link href="/queue" style={{ fontSize: 12, color: "var(--gray-400)", textDecoration: "none", whiteSpace: "nowrap" }}>
          ← Queue
        </Link>

        {/* Mode tabs */}
        <div style={{ display: "flex", gap: 4, flex: 1, flexWrap: "wrap" }}>
          {MODE_TABS.map(tab => (
            <button key={tab.id} onClick={() => { setMode(tab.id); setPage(1); }}
              title={tab.desc}
              style={{
                padding: "6px 14px", borderRadius: 8, border: "none", cursor: "pointer", fontSize: 12,
                fontWeight: mode === tab.id ? 600 : 400,
                background: mode === tab.id ? "var(--rose)" : "var(--gray-100)",
                color: mode === tab.id ? "#fff" : "var(--gray-500)",
                transition: "all 0.15s",
              }}>
              {tab.label}
            </button>
          ))}
        </div>

        {/* Progress pill */}
        {data && mode !== "fulltext" && (
          <span style={{
            fontSize: 11, fontFamily: "JetBrains Mono",
            color: allDone ? "var(--green)" : "var(--gray-400)",
            background: allDone ? "var(--green-light)" : "var(--gray-100)",
            border: `1px solid ${allDone ? "var(--green-border)" : "var(--gray-200)"}`,
            padding: "4px 10px", borderRadius: 99, whiteSpace: "nowrap",
          }}>
            {done}/{total} done
          </span>
        )}

        {/* Compact auto-translate */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
          <select value={provider}
            onChange={e => { setProvider(e.target.value as Provider); localStorage.setItem("omi_provider", e.target.value); }}
            style={{ padding: "5px 8px", borderRadius: 7, border: "1px solid var(--gray-200)", fontSize: 11, color: "var(--gray-600)", background: "var(--white)", outline: "none" }}>
            <option value="youtube">YouTube (free)</option>
            <option value="sarvam">Sarvam AI</option>
            <option value="openrouter">OpenRouter</option>
          </select>
          {provider === "openrouter" && (
            <select value={modelPreset}
              onChange={e => { setModelPreset(e.target.value); localStorage.setItem("omi_model", e.target.value); }}
              style={{ padding: "5px 8px", borderRadius: 7, border: "1px solid var(--gray-200)", fontSize: 11, color: "var(--gray-600)", background: "var(--white)", outline: "none" }}>
              {PRESETS.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
          )}
          {provider === "openrouter" && modelPreset === "custom" && (
            <input type="text" value={customModel}
              onChange={e => { setCustomModel(e.target.value); localStorage.setItem("omi_model", e.target.value); }}
              placeholder="org/model"
              style={{ padding: "5px 8px", borderRadius: 7, border: "1px solid var(--rose-border)", fontSize: 11, fontFamily: "JetBrains Mono", color: "var(--gray-900)", outline: "none", width: 140 }} />
          )}
          <motion.button onClick={autoTranslate} disabled={translating}
            whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
            style={{
              padding: "5px 14px", borderRadius: 7, border: "none", fontSize: 11, fontWeight: 600,
              background: "var(--rose)", color: "#fff", cursor: "pointer", opacity: translating ? 0.5 : 1,
              whiteSpace: "nowrap",
            }}>
            {translating ? "Translating…" : "✦ Auto-translate"}
          </motion.button>
        </div>
      </div>

      {/* Translate result banner */}
      <AnimatePresence>
        {txResult && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
            style={{ padding: "8px 14px", borderRadius: 8, background: "var(--green-light)", border: "1px solid var(--green-border)", fontSize: 12, color: "var(--green)", marginBottom: 12 }}>
            ✓ {txResult.message}
          </motion.div>
        )}
        {txError && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
            style={{ padding: "8px 14px", borderRadius: 8, background: "#fef2f2", border: "1px solid #fecaca", fontSize: 12, color: "var(--red)", marginBottom: 12 }}>
            ✗ {txError}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Embedded YouTube Player ── */}
      <YouTubePlayer ref={playerRef} videoId={videoId} />

      {/* ── Mode content ── */}
      {mode === "fulltext" && <FullTextMode videoId={videoId} seekTo={handleSeekTo} />}
      {mode === "sentences" && (
        <SentencesMode videoId={videoId} page={page} setPage={setPage}
          data={data} isLoading={isLoading} error={error} handleUpdate={handleUpdate}
          seekTo={handleSeekTo} translatingSegId={translatingSegId}
          onTranslate={translateSegment} />
      )}
      {mode === "finetune" && (
        <FineTuneMode videoId={videoId} page={page} setPage={setPage}
          data={data} isLoading={isLoading} error={error} handleUpdate={handleUpdate}
          seekTo={handleSeekTo} translatingSegId={translatingSegId}
          onTranslate={translateSegment} />
      )}

      {/* ── Bottom bar: export + mark reviewed (sentence + finetune only) ── */}
      {mode !== "fulltext" && (
        <div style={{
          display: "flex", alignItems: "center", gap: 12, marginTop: 20,
          paddingTop: 16, borderTop: "1px solid var(--gray-100)", flexWrap: "wrap",
        }}>
          <span style={{ fontSize: 12, color: "var(--gray-400)", flex: 1 }}>
            Ctrl+Enter or click away to save each edit.
          </span>
          {data && !allDone && (
            <motion.button onClick={markPageReviewed} disabled={markingAll}
              whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }}
              style={{ padding: "7px 16px", borderRadius: 8, border: "1px solid var(--amber-border)", background: "var(--amber-light)", color: "var(--amber)", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
              {markingAll ? "Marking…" : "✓ Mark page done"}
            </motion.button>
          )}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <select value={exportFormat} onChange={e => setExportFormat(e.target.value as typeof exportFormat)}
              style={{ padding: "6px 8px", borderRadius: 8, border: "1px solid var(--gray-200)", fontSize: 11, color: "var(--gray-500)", background: "var(--white)", outline: "none" }}>
              <option value="raw">Raw pairs</option>
              <option value="alpaca">Alpaca</option>
              <option value="openai">OpenAI</option>
            </select>
            <a href={`/api/v1/export/jsonl?youtube_id=${videoId}&reviewed_only=true&format=${exportFormat}`}
              style={{ padding: "6px 14px", borderRadius: 8, border: "1px solid var(--green-border)", background: "var(--green-light)", color: "var(--green)", fontSize: 12, fontWeight: 600, textDecoration: "none" }}>
              ↓ Export Gold
            </a>
            <a href={`/api/v1/export/jsonl?youtube_id=${videoId}&format=${exportFormat}`}
              style={{ padding: "6px 14px", borderRadius: 8, border: "1px solid var(--gray-200)", background: "var(--white)", color: "var(--gray-500)", fontSize: 12, textDecoration: "none" }}>
              ↓ Export all
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
