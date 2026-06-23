"use client";
import { useState } from "react";
import axios from "axios";
import { motion } from "motion/react";
import Link from "next/link";

interface UploadResponse {
  message_id: number;
  title: string;
  source_type: string;
  chunk_count: number;
  language: string;
}

export default function UploadPage() {
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [sourceType, setSourceType] = useState("Article");
  const [sourceUrl, setSourceUrl] = useState("");
  const [language, setLanguage] = useState("Telugu");
  const [content, setContent] = useState("");
  const [state, setState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [msg, setMsg] = useState("");
  const [result, setResult] = useState<UploadResponse | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !content.trim()) {
      setState("error");
      setMsg("Title and Content are required.");
      return;
    }
    setState("loading");
    setMsg("");
    setResult(null);
    try {
      const { data } = await axios.post<UploadResponse>("/api/v1/documents/upload", {
        title: title.trim(),
        author: author.trim() || null,
        source_type: sourceType.toLowerCase(),
        source_url: sourceUrl.trim() || null,
        language: language.toLowerCase(),
        content: content.trim(),
      });
      setState("success");
      setMsg(`Uploaded — ${data.chunk_count} chunks created.`);
      setResult(data);
    } catch (err: unknown) {
      setState("error");
      const m = axios.isAxiosError(err) ? err.response?.data?.detail ?? err.message : String(err);
      setMsg(typeof m === "string" ? m : JSON.stringify(m));
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%",
    border: "1px solid var(--warm-200)",
    borderRadius: 10,
    padding: "10px 14px",
    fontSize: 14,
    color: "var(--ink)",
    background: "var(--white)",
    fontFamily: "Plus Jakarta Sans",
    outline: "none",
    transition: "border-color 0.15s",
  };

  const labelStyle: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 600,
    color: "var(--ink-2)",
    letterSpacing: "0.03em",
    marginBottom: 6,
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 48 }}>

      {/* Hero heading */}
      <div style={{ textAlign: "center", paddingTop: 24 }}>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        >
          <p style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.12em", color: "var(--gold)", textTransform: "uppercase", marginBottom: 12 }}>
            Import content
          </p>
          <h1 className="font-display" style={{ fontSize: 40, color: "var(--ink)", lineHeight: 1.15, letterSpacing: "-0.02em", marginBottom: 8 }}>
            Upload Document
          </h1>
          <p style={{ fontSize: 15, color: "var(--ink-2)", marginBottom: 36, maxWidth: 460, margin: "0 auto 36px" }}>
            Import articles, books, and audio transcripts.
          </p>
        </motion.div>
      </div>

      {/* Upload form */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
      >
        <form
          onSubmit={handleSubmit}
          style={{
            maxWidth: 640,
            margin: "0 auto",
            display: "flex",
            flexDirection: "column",
            gap: 20,
            background: "var(--white)",
            borderRadius: 14,
            boxShadow: "var(--shadow-card)",
            border: "1px solid var(--warm-200)",
            padding: 28,
          }}
        >
          {/* Title */}
          <div>
            <label style={labelStyle}>Title *</label>
            <input
              type="text"
              value={title}
              onChange={() => { if (state !== "idle") { setState("idle"); setMsg(""); } }}
              onInput={(e) => setTitle((e.target as HTMLInputElement).value)}
              placeholder="Sermon title or document name"
              required
              style={inputStyle}
            />
          </div>

          {/* Author */}
          <div>
            <label style={labelStyle}>Author</label>
            <input
              type="text"
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              placeholder="Pastor or author name"
              style={inputStyle}
            />
          </div>

          {/* Source Type + Language row */}
          <div style={{ display: "flex", gap: 16 }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Source Type</label>
              <select
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value)}
                style={inputStyle}
              >
                <option value="Article">Article</option>
                <option value="Book">Book</option>
                <option value="Audio">Audio</option>
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Language</label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                style={inputStyle}
              >
                <option value="Telugu">Telugu</option>
                <option value="English">English</option>
              </select>
            </div>
          </div>

          {/* Source URL */}
          <div>
            <label style={labelStyle}>Source URL</label>
            <input
              type="url"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://example.com/article"
              style={inputStyle}
            />
          </div>

          {/* Content */}
          <div>
            <label style={labelStyle}>Content *</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Paste full text or transcript here…"
              required
              rows={16}
              style={{ ...inputStyle, resize: "vertical", lineHeight: 1.7, fontFamily: "DM Sans" }}
            />
          </div>

          {/* Submit */}
          <motion.button
            type="submit"
            disabled={state === "loading" || !title.trim() || !content.trim()}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            style={{
              padding: "12px 22px",
              borderRadius: 10,
              border: "none",
              background: "var(--ink)",
              color: "var(--white)",
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
              fontFamily: "Plus Jakarta Sans",
              opacity: state === "loading" || !title.trim() || !content.trim() ? 0.5 : 1,
            }}
          >
            {state === "loading" ? "Uploading…" : "Upload →"}
          </motion.button>

          {/* Messages */}
          {state === "success" && result && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              style={{
                padding: "12px 16px",
                borderRadius: 10,
                background: "var(--green-light)",
                border: "1px solid var(--green-border)",
                fontSize: 13,
                color: "var(--green)",
              }}
            >
              ✓ {msg}
              <div style={{ marginTop: 8 }}>
                <Link
                  href="/search"
                  style={{ fontSize: 13, fontWeight: 600, color: "var(--green)", textDecoration: "underline" }}
                >
                  Search documents →
                </Link>
              </div>
            </motion.div>
          )}
          {state === "error" && (
            <motion.p
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              style={{ fontSize: 13, color: "var(--red)" }}
            >
              ✗ {msg}
            </motion.p>
          )}
        </form>
      </motion.div>
    </div>
  );
}
