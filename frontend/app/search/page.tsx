"use client";
import { useState, useCallback } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "motion/react";
import Link from "next/link";

interface SearchResult {
  chunk_id: number;
  chunk_text: string;
  message_id: number;
  score: number;
  video: { youtube_id: string; title: string; channel: string };
}
interface SearchResponse { results: SearchResult[]; total: number }

interface AskSource {
  index: number;
  chunk_id: number;
  chunk_text: string;
  video: { youtube_id: string; title: string; channel: string };
}
interface AskResponse {
  answer: string;
  sources: AskSource[];
  search_latency_ms: number;
  generation_latency_ms: number;
}

type Mode = "search" | "ask";

export default function SearchPage() {
  const [mode, setMode] = useState<Mode>("search");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [searchResults, setSearchResults] = useState<SearchResponse | null>(null);
  const [askResult, setAskResult] = useState<AskResponse | null>(null);

  const handleSearch = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setSearchResults(null);
    setAskResult(null);
    try {
      const { data } = await axios.post<SearchResponse>("/api/v1/search", { query: q, top_k: 10 });
      setSearchResults(data);
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail ?? err.message : String(err);
      setError(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setLoading(false);
    }
  }, [query]);

  const handleAsk = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setSearchResults(null);
    setAskResult(null);
    try {
      const { data } = await axios.post<AskResponse>("/api/v1/ask", { query: q });
      setAskResult(data);
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail ?? err.message : String(err);
      setError(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setLoading(false);
    }
  }, [query]);

  function handleModeSwitch(m: Mode) {
    setMode(m);
    setQuery("");
    setError(null);
    setSearchResults(null);
    setAskResult(null);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 40 }}>

      {/* Header */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}>
        <p style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.12em", color: "var(--gold)", textTransform: "uppercase", marginBottom: 12 }}>
          Explore · Query · Discover
        </p>
        <h1 className="font-display" style={{ fontSize: 36, color: "var(--ink)", lineHeight: 1.15, letterSpacing: "-0.02em", marginBottom: 8 }}>
          {mode === "search" ? "Semantic Search" : "Ask a Question"}
        </h1>
        <p style={{ fontSize: 15, color: "var(--ink-2)", maxWidth: 520 }}>
          {mode === "search"
            ? "Find relevant sermon passages across the entire translation dataset."
            : "Ask anything about the sermons and get an answer with cited sources."}
        </p>
      </motion.div>

      {/* Mode toggle */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.08 }} style={{ display: "flex", gap: 4, padding: 4, background: "var(--warm-100)", borderRadius: 10, width: "fit-content" }}>
        {([["search", "Search"], ["ask", "Ask"]] as const).map(([m, label]) => (
          <button key={m} onClick={() => handleModeSwitch(m)} style={{
            padding: "8px 20px", borderRadius: 8, border: "none", fontSize: 13, fontWeight: 600, cursor: "pointer",
            fontFamily: "Plus Jakarta Sans, DM Sans, sans-serif",
            background: mode === m ? "var(--white)" : "transparent",
            color: mode === m ? "var(--ink)" : "var(--ink-3)",
            boxShadow: mode === m ? "var(--shadow-sm)" : "none",
            transition: "all 0.15s",
          }}>
            {label}
          </button>
        ))}
      </motion.div>

      {/* Input form */}
      <motion.form
        onSubmit={mode === "search" ? handleSearch : handleAsk}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.14 }}
        style={{
          display: "flex", gap: 10, padding: "6px 6px 6px 20px",
          background: "var(--white)", borderRadius: 14,
          boxShadow: "0 4px 24px rgba(0,0,0,0.08), 0 1px 3px rgba(0,0,0,0.06)",
          border: "1px solid var(--warm-200)", maxWidth: 680,
        }}
      >
        <input
          type="text" value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={mode === "search" ? "Search sermons..." : "Ask a question about the sermons..."}
          style={{
            flex: 1, border: "none", outline: "none", fontSize: 14, color: "var(--ink)",
            background: "transparent", fontFamily: "Plus Jakarta Sans, DM Sans, sans-serif",
          }}
        />
        <motion.button type="submit"
          disabled={loading || !query.trim()}
          whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
          style={{
            padding: "10px 24px", borderRadius: 10, border: "none",
            background: "var(--ink)", color: "var(--white)",
            fontSize: 13, fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap",
            fontFamily: "Plus Jakarta Sans, DM Sans, sans-serif",
            opacity: (loading || !query.trim()) ? 0.5 : 1,
          }}
        >
          {loading ? "Searching…" : mode === "search" ? "Search →" : "Ask →"}
        </motion.button>
      </motion.form>

      {/* Error */}
      <AnimatePresence>
        {error && (
          <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            style={{ fontSize: 13, color: "var(--red)", background: "var(--red-light)", padding: "10px 16px", borderRadius: 10, maxWidth: 680 }}>
            ✗ {error}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Loading */}
      <AnimatePresence>
        {loading && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--ink-3)", fontSize: 13, padding: "32px 0" }}>
            <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
              style={{ width: 16, height: 16, border: "2px solid var(--warm-200)", borderTopColor: "var(--rose)", borderRadius: "50%" }} />
            {mode === "search" ? "Searching the sermon database…" : "Thinking through your question…"}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Search results */}
      {!loading && searchResults && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
          <p style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 16 }}>
            {searchResults.total} result{searchResults.total !== 1 ? "s" : ""} found
          </p>

          {searchResults.results.length === 0 ? (
            <div style={{ padding: "56px 0", textAlign: "center" }}>
              <p className="font-display" style={{ fontSize: 18, color: "var(--ink-3)", marginBottom: 6 }}>No results</p>
              <p style={{ fontSize: 13, color: "var(--ink-4)" }}>Try a different query or check spelling.</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {searchResults.results.map((r, i) => (
                <motion.div key={r.chunk_id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.04, duration: 0.3 }}
                  style={{
                    background: "var(--white)", borderRadius: 12, padding: "18px 22px",
                    boxShadow: "var(--shadow-card)", border: "1px solid var(--warm-200)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ fontSize: 14, fontWeight: 600, color: "var(--ink)", lineHeight: 1.35 }}>
                        {r.video.title || "Untitled"}
                      </p>
                      <p style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>
                        {r.video.channel || "Unknown channel"}
                      </p>
                    </div>
                    <span style={{
                      flexShrink: 0, marginLeft: 12, fontSize: 12, fontWeight: 600,
                      fontFamily: "JetBrains Mono, monospace",
                      padding: "3px 10px", borderRadius: 20,
                      background: r.score >= 0.8 ? "var(--green-light)" : r.score >= 0.5 ? "var(--amber-light)" : "var(--warm-100)",
                      color: r.score >= 0.8 ? "var(--green)" : r.score >= 0.5 ? "var(--amber)" : "var(--ink-3)",
                    }}>
                      {(r.score * 100).toFixed(1)}%
                    </span>
                  </div>
                  <p style={{
                    fontSize: 13, color: "var(--ink-2)", lineHeight: 1.55,
                    display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden",
                  }}>
                    {r.chunk_text.length > 200 ? r.chunk_text.slice(0, 200) + "…" : r.chunk_text}
                  </p>
                  <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 12 }}>
                    <Link href={`https://youtube.com/watch?v=${r.video.youtube_id}`} target="_blank" rel="noopener noreferrer"
                      style={{ fontSize: 12, fontWeight: 600, color: "var(--rose)", textDecoration: "none" }}>
                      Watch on YouTube ↗
                    </Link>
                    <span style={{ fontSize: 11, color: "var(--ink-4)", fontFamily: "JetBrains Mono, monospace" }}>
                      {r.video.youtube_id}
                    </span>
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </motion.div>
      )}

      {/* Ask result */}
      {!loading && askResult && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }} style={{ display: "flex", flexDirection: "column", gap: 24, maxWidth: 680 }}>

          {/* Answer */}
          <div style={{
            background: "var(--white)", borderRadius: 14, padding: "24px 28px",
            boxShadow: "0 4px 24px rgba(0,0,0,0.08), 0 1px 3px rgba(0,0,0,0.06)",
            border: "1px solid var(--warm-200)",
          }}>
            <p style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.1em", color: "var(--gold)", textTransform: "uppercase", marginBottom: 10 }}>
              Answer
            </p>
            <p style={{ fontSize: 15, color: "var(--ink)", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
              {askResult.answer}
            </p>
          </div>

          {/* Latency */}
          <div style={{ display: "flex", gap: 16, fontSize: 12, color: "var(--ink-3)", fontFamily: "JetBrains Mono, monospace" }}>
            <span>Search: {askResult.search_latency_ms}ms</span>
            <span>Generation: {askResult.generation_latency_ms}ms</span>
            <span>Total: {askResult.search_latency_ms + askResult.generation_latency_ms}ms</span>
          </div>

          {/* Sources */}
          {askResult.sources.length > 0 && (
            <div>
              <p style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-3)", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 12 }}>
                Sources ({askResult.sources.length})
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {askResult.sources.map((s) => (
                  <div key={s.chunk_id} style={{
                    background: "var(--white)", borderRadius: 10, padding: "14px 18px",
                    boxShadow: "var(--shadow-card)", border: "1px solid var(--warm-200)",
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                      <p style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>
                        {s.video.title || "Untitled"}
                      </p>
                      <span style={{ fontSize: 11, color: "var(--ink-4)", fontFamily: "JetBrains Mono, monospace" }}>
                        #{s.index}
                      </span>
                    </div>
                    <p style={{
                      fontSize: 12, color: "var(--ink-2)", lineHeight: 1.5,
                      display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
                    }}>
                      {s.chunk_text.length > 200 ? s.chunk_text.slice(0, 200) + "…" : s.chunk_text}
                    </p>
                    <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 10 }}>
                      <Link href={`https://youtube.com/watch?v=${s.video.youtube_id}`} target="_blank" rel="noopener noreferrer"
                        style={{ fontSize: 12, fontWeight: 600, color: "var(--rose)", textDecoration: "none" }}>
                        Watch on YouTube ↗
                      </Link>
                      <span style={{ fontSize: 11, color: "var(--ink-4)", fontFamily: "JetBrains Mono, monospace" }}>
                        {s.video.youtube_id}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </motion.div>
      )}

      {/* Empty state */}
      {!loading && !error && !searchResults && !askResult && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}
          style={{ padding: "64px 0", textAlign: "center" }}>
          <p className="font-display" style={{ fontSize: 18, color: "var(--ink-3)", marginBottom: 6 }}>
            {mode === "search" ? "Search the sermon database" : "Ask a question"}
          </p>
          <p style={{ fontSize: 13, color: "var(--ink-4)" }}>
            {mode === "search"
              ? "Type a topic, phrase, or theological term to find relevant passages."
              : "Ask in natural language — the engine will search and generate an answer."}
          </p>
        </motion.div>
      )}
    </div>
  );
}
