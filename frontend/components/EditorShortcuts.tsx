"use client";
import { useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import type { Segment } from "@/app/editor/[videoId]/page";

export const CONTENT_TYPE_DEFAULT = "sermon";
export const CONTENT_TYPE_SONG = "song";

interface ShortcutHandlers {
  patchSegment: (id: number, patch: Partial<Segment>) => void;
  setFocusedId: (id: number | null) => void;
  setShowHelp: (open: boolean) => void;
}

export function useEditorShortcuts(
  enabled: boolean,
  items: Segment[],
  focusedId: number | null,
  handlers: ShortcutHandlers,
): void {
  useEffect(() => {
    if (!enabled) return undefined;

    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      if (t) {
        const tag = t.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || t.isContentEditable) {
          return;
        }
      }
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      if (!items.length) return;

      const idx = focusedId == null ? -1 : items.findIndex(s => s.id === focusedId);

      if (e.key === "?" || (e.key === "/" && e.shiftKey)) {
        e.preventDefault();
        handlers.setShowHelp(true);
        return;
      }

      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        const next = idx < 0 ? 0 : Math.min(items.length - 1, idx + 1);
        handlers.setFocusedId(items[next].id);
        return;
      }

      if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        const next = idx <= 0 ? 0 : idx - 1;
        handlers.setFocusedId(items[next].id);
        return;
      }

      if (idx < 0) return;
      const cur = items[idx];

      if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        handlers.patchSegment(cur.id, { is_reviewed: !cur.is_reviewed });
        return;
      }

      if (e.key >= "1" && e.key <= "5") {
        e.preventDefault();
        handlers.patchSegment(cur.id, { quality_score: Number(e.key) });
        return;
      }

      if (e.key === "s" || e.key === "S") {
        e.preventDefault();
        const next = cur.content_type === CONTENT_TYPE_SONG ? CONTENT_TYPE_DEFAULT : CONTENT_TYPE_SONG;
        handlers.patchSegment(cur.id, { content_type: next });
      }
    }

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled, items, focusedId, handlers]);
}

// ── Help overlay ───────────────────────────────────────────────────────────

const SHORTCUTS: { keys: string; description: string }[] = [
  { keys: "j / ↓", description: "Focus next segment" },
  { keys: "k / ↑", description: "Focus previous segment" },
  { keys: "r", description: "Toggle reviewed on focused segment" },
  { keys: "1 – 5", description: "Set quality score on focused segment" },
  { keys: "s", description: "Toggle song flag (song ↔ sermon)" },
  { keys: "?", description: "Show this help" },
  { keys: "Esc", description: "Close help / clear focus" },
];

export function EditorHelpOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  useEffect(() => {
    if (!open) return undefined;
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          onClick={onClose}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          style={{
            position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.45)",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: 100, backdropFilter: "blur(2px)",
          }}
        >
          <motion.div
            onClick={e => e.stopPropagation()}
            initial={{ opacity: 0, y: 10, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 360, damping: 28 }}
            style={{
              background: "var(--white)", borderRadius: 14, padding: "22px 28px",
              minWidth: 360, maxWidth: 460, border: "1px solid var(--gray-200)",
              boxShadow: "0 24px 48px -12px rgba(15, 23, 42, 0.25)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <p style={{ fontSize: 13, fontWeight: 700, color: "var(--gray-900)", margin: 0, letterSpacing: "-0.01em" }}>
                Keyboard shortcuts
              </p>
              <button onClick={onClose} aria-label="Close help"
                style={{ background: "none", border: "none", fontSize: 16, color: "var(--gray-400)", cursor: "pointer", padding: 0, lineHeight: 1 }}>
                ✕
              </button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {SHORTCUTS.map(s => (
                <div key={s.keys} style={{ display: "flex", alignItems: "center", gap: 14 }}>
                  <kbd style={{
                    fontFamily: "JetBrains Mono", fontSize: 11, padding: "3px 8px",
                    borderRadius: 6, border: "1px solid var(--gray-200)", background: "var(--gray-50)",
                    color: "var(--gray-700)", minWidth: 70, textAlign: "center",
                  }}>
                    {s.keys}
                  </kbd>
                  <span style={{ fontSize: 12, color: "var(--gray-500)" }}>{s.description}</span>
                </div>
              ))}
            </div>
            <p style={{ fontSize: 10, color: "var(--gray-400)", marginTop: 18, marginBottom: 0 }}>
              Shortcuts are disabled while typing in a textarea or input.
            </p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ── Bulk action toolbar ────────────────────────────────────────────────────

export interface BulkToolbarProps {
  count: number;
  busy: boolean;
  onMarkReviewed: () => void;
  onSetQuality: (q: number) => void;
  onFlagSong: () => void;
  onClearSong: () => void;
  onShowHelp: () => void;
  onClear: () => void;
}

export function EditorBulkToolbar(props: BulkToolbarProps) {
  return (
    <AnimatePresence>
      {props.count >= 2 && (
        <motion.div
          initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
          style={{
            display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
            padding: "10px 14px", marginBottom: 12, borderRadius: 10,
            border: "1px solid var(--rose-border, #fecdd3)", background: "rgba(244,63,94,0.04)",
          }}
        >
          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--rose)" }}>
            {props.count} selected
          </span>
          <button onClick={props.onMarkReviewed} disabled={props.busy}
            style={btnPrimary(props.busy)}>
            ✓ Mark reviewed
          </button>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--gray-500)" }}>
            Quality:
            <select onChange={e => { const v = Number(e.target.value); if (v) props.onSetQuality(v); e.currentTarget.value = ""; }}
              disabled={props.busy} defaultValue=""
              style={{ padding: "4px 8px", borderRadius: 6, border: "1px solid var(--gray-200)", fontSize: 11, background: "var(--white)", outline: "none" }}>
              <option value="" disabled>Set…</option>
              <option value="1">1</option>
              <option value="2">2</option>
              <option value="3">3</option>
              <option value="4">4</option>
              <option value="5">5</option>
            </select>
          </label>
          <button onClick={props.onFlagSong} disabled={props.busy} style={btnSecondary(props.busy)}>
            🎵 Flag song
          </button>
          <button onClick={props.onClearSong} disabled={props.busy} style={btnSecondary(props.busy)}>
            Clear song
          </button>
          <button onClick={props.onShowHelp} disabled={props.busy} style={btnGhost(props.busy)}
            title="Show keyboard shortcuts">
            ?
          </button>
          <button onClick={props.onClear} disabled={props.busy} style={{ ...btnGhost(props.busy), marginLeft: "auto" }}>
            Clear
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function btnPrimary(busy: boolean): React.CSSProperties {
  return {
    padding: "5px 12px", borderRadius: 7, border: "none", fontSize: 11, fontWeight: 600,
    background: "var(--rose)", color: "#fff", cursor: busy ? "not-allowed" : "pointer",
    opacity: busy ? 0.5 : 1,
  };
}

function btnSecondary(busy: boolean): React.CSSProperties {
  return {
    padding: "5px 10px", borderRadius: 7, border: "1px solid var(--gray-200)", fontSize: 11,
    background: "var(--white)", color: "var(--gray-600)", cursor: busy ? "not-allowed" : "pointer",
    opacity: busy ? 0.5 : 1,
  };
}

function btnGhost(busy: boolean): React.CSSProperties {
  return {
    padding: "5px 9px", borderRadius: 7, border: "1px solid transparent", fontSize: 11,
    background: "transparent", color: "var(--gray-500)", cursor: busy ? "not-allowed" : "pointer",
    opacity: busy ? 0.5 : 1,
  };
}
