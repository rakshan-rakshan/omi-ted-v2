"use client";
import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import axios from "axios";

interface Props {
  open: boolean;
  youtubeId: string | null;
  scope: "ingest" | "translation";
  title?: string | null;
  onClose: () => void;
  onRemoved: () => void;
}

export default function RemoveDialog({ open, youtubeId, scope, title, onClose, onRemoved }: Props) {
  const [reason, setReason]       = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  // Clear reason + error whenever the dialog opens or closes.
  useEffect(() => {
    if (!open) { setReason(""); setError(null); setSubmitting(false); }
  }, [open]);

  function handleClose() {
    if (submitting) return;
    setReason("");
    setError(null);
    onClose();
  }

  async function handleRemove() {
    if (!youtubeId) return;
    setSubmitting(true);
    setError(null);
    try {
      await axios.post(`/api/v1/videos/${youtubeId}/remove`, {
        scope,
        reason: reason.trim() || null,
      });
      onRemoved();
      setReason("");
      onClose();
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err)
        ? err.response?.data?.detail ?? err.message
        : String(err);
      setError(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setSubmitting(false);
    }
  }

  const subject = title || youtubeId || "";

  return (
    <AnimatePresence>
      {open && (
        <motion.div ref={ref}
          onClick={(e) => { if (e.target === ref.current) handleClose(); }}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          style={{
            position: "fixed", inset: 0, zIndex: 100,
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: 24, background: "rgba(17,24,39,0.35)", backdropFilter: "blur(4px)",
          }}>
          <motion.div
            initial={{ opacity: 0, y: 14, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 420, damping: 30 }}
            style={{
              width: "100%", maxWidth: 460,
              background: "var(--white)", borderRadius: 16,
              boxShadow: "0 20px 60px rgba(0,0,0,0.12), 0 4px 12px rgba(0,0,0,0.06)",
              overflow: "hidden", border: "1px solid var(--gray-200)",
            }}>

            {/* Header */}
            <div style={{ padding: "22px 26px 18px", borderBottom: "1px solid var(--gray-100)" }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                <div style={{ minWidth: 0 }}>
                  <h2 style={{ fontSize: 18, fontWeight: 600, color: "var(--gray-900)", margin: 0 }}>
                    Remove from {scope}
                  </h2>
                  <p style={{ fontSize: 12, color: "var(--gray-400)", marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {subject}
                  </p>
                </div>
                <button onClick={handleClose} aria-label="Close" title="Close"
                  style={{
                    background: "none", border: "none", cursor: submitting ? "not-allowed" : "pointer",
                    color: "var(--gray-400)", fontSize: 20, padding: "2px 6px", lineHeight: 1,
                    borderRadius: 6, flexShrink: 0,
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "var(--gray-100)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "none")}>
                  ×
                </button>
              </div>
            </div>

            {/* Body */}
            <div style={{ padding: "20px 26px 24px", display: "flex", flexDirection: "column", gap: 14 }}>
              <p style={{ fontSize: 13, color: "var(--ink-2)", margin: 0, lineHeight: 1.5 }}>
                This hides the video from the {scope} list. You can restore it any time from the Removed bin.
              </p>

              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={3}
                aria-label="Reason for removal"
                placeholder="Reason (optional) — e.g. duplicate, wrong language, low quality"
                style={{
                  width: "100%", padding: "10px 12px", borderRadius: 8,
                  border: "1px solid var(--gray-200)", background: "var(--gray-50)",
                  fontSize: 13, fontFamily: "'DM Sans', ui-sans-serif, sans-serif",
                  color: "var(--gray-900)", outline: "none", resize: "vertical",
                  lineHeight: 1.5,
                }}
                onFocus={(e) => { e.target.style.borderColor = "var(--rose)"; e.target.style.boxShadow = "0 0 0 3px rgba(244,63,94,0.08)"; }}
                onBlur={(e)  => { e.target.style.borderColor = "var(--gray-200)"; e.target.style.boxShadow = "none"; }}
              />

              {error && (
                <p style={{ fontSize: 11, color: "var(--red)", margin: "-4px 0 0" }}>{error}</p>
              )}

              <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 2 }}>
                <button onClick={handleClose} disabled={submitting}
                  style={{
                    padding: "9px 16px", borderRadius: 10, cursor: submitting ? "not-allowed" : "pointer",
                    fontSize: 13, fontWeight: 600, border: "1px solid var(--gray-200)",
                    background: "var(--white)", color: "var(--ink-2)", opacity: submitting ? 0.5 : 1,
                  }}>
                  Cancel
                </button>
                <motion.button onClick={handleRemove}
                  disabled={submitting || !youtubeId}
                  whileHover={{ scale: submitting ? 1 : 1.01 }} whileTap={{ scale: submitting ? 1 : 0.98 }}
                  style={{
                    padding: "9px 18px", borderRadius: 10, border: "none",
                    cursor: submitting ? "not-allowed" : "pointer", fontSize: 13, fontWeight: 600,
                    background: "var(--red)", color: "#fff",
                    opacity: (submitting || !youtubeId) ? 0.5 : 1,
                  }}>
                  {submitting ? "Removing…" : "Remove"}
                </motion.button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
