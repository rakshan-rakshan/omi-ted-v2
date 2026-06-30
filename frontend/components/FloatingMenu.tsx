"use client";
import { useEffect, useRef } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  /** Viewport coords to anchor near (e.g. a text selection). If null → centered panel. */
  anchor?: { x: number; y: number } | null;
  width?: number;
  closeOnScroll?: boolean;
  children: React.ReactNode;
}

/**
 * Floating, auto-hidden panel. Hides on outside-click, Escape, and (optionally)
 * window scroll. Anchored near a point, or centered when no anchor is given.
 */
export default function FloatingMenu({
  open, onClose, anchor = null, width = 360, closeOnScroll = true, children,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    const onScroll = () => onClose();
    // defer so the click that opened the menu doesn't immediately close it
    const t = setTimeout(() => {
      document.addEventListener("mousedown", onDown);
      document.addEventListener("keydown", onKey);
      if (closeOnScroll) window.addEventListener("scroll", onScroll, true);
    }, 0);
    return () => {
      clearTimeout(t);
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open, onClose, closeOnScroll]);

  if (!open) return null;

  const vw = typeof window !== "undefined" ? window.innerWidth : 1280;
  const w = Math.min(width, vw - 24);
  const style: React.CSSProperties = anchor
    ? { position: "fixed", left: Math.max(12, Math.min(anchor.x, vw - w - 12)), top: anchor.y + 8 }
    : { position: "fixed", left: "50%", top: "8vh", transform: "translateX(-50%)" };

  return (
    <div ref={ref} style={{
      ...style, width: w, maxWidth: "calc(100vw - 24px)", maxHeight: "82vh",
      overflowY: "auto", background: "var(--white)", border: "1px solid var(--warm-200)",
      borderRadius: 12, boxShadow: "0 10px 44px rgba(0,0,0,0.20)", zIndex: 70, padding: 14,
    }}>
      {children}
    </div>
  );
}
