"use client";
import { useEffect, useState } from "react";
import axios from "axios";
import FloatingMenu from "./FloatingMenu";

interface Cand { te_term: string; meanings: string[]; category: string; sources: string[]; }
interface EditCand extends Cand { selected: boolean; meaningsStr: string; }

const CATS = ["theology", "name", "place", "general"];
const TE_RE = /[ఀ-౿]/;
const errMsg = (e: unknown) =>
  axios.isAxiosError(e) ? (e.response?.data?.detail ?? e.message) : String(e);

/**
 * One-click glossary tools for a video:
 *  - "Generate glossary" → LLM + heuristic extraction → review/edit candidates → bulk-save.
 *  - Select any Telugu text → floating "Add to glossary" → quick add (term → many meanings).
 * Mount once in the editor: <GlossaryTools videoId={youtubeId} />
 */
export default function GlossaryTools({ videoId }: { videoId: string }) {
  const [genOpen, setGenOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [cands, setCands] = useState<EditCand[]>([]);
  const [msg, setMsg] = useState("");

  const [selMenu, setSelMenu] = useState<{ x: number; y: number; text: string } | null>(null);
  const [addForm, setAddForm] = useState<{ term: string; meanings: string; category: string } | null>(null);

  async function generate() {
    setLoading(true); setMsg(""); setGenOpen(true); setCands([]);
    try {
      const { data } = await axios.post(`/api/v1/videos/${videoId}/glossary/extract?methods=llm,heuristic`);
      setCands((data.candidates || []).map((c: Cand) => ({
        ...c, selected: c.meanings.length > 0, meaningsStr: c.meanings.join(", "),
      })));
      if (!data.candidates?.length) setMsg("No candidate terms found.");
    } catch (e) { setMsg(errMsg(e)); } finally { setLoading(false); }
  }

  function patch(i: number, p: Partial<EditCand>) {
    setCands((cs) => cs.map((c, j) => (j === i ? { ...c, ...p } : c)));
  }

  async function saveSelected() {
    const terms = cands
      .filter((c) => c.selected)
      .map((c) => ({
        te_term: c.te_term,
        meanings: c.meaningsStr.split(",").map((s) => s.trim()).filter(Boolean),
        category: c.category,
      }))
      .filter((t) => t.meanings.length > 0);
    if (!terms.length) { setMsg("Select at least one term with a meaning."); return; }
    try {
      const { data } = await axios.post("/api/v1/glossary/bulk", { terms });
      setMsg(`Saved: ${data.created} new · ${data.updated} updated.`);
      setTimeout(() => setGenOpen(false), 1000);
    } catch (e) { setMsg(errMsg(e)); }
  }

  // ── select-to-add (Telugu selections only) ──
  useEffect(() => {
    const onUp = () => {
      const sel = window.getSelection();
      const text = sel?.toString().trim() ?? "";
      if (text.length >= 2 && text.length <= 60 && TE_RE.test(text) && sel && sel.rangeCount > 0) {
        const rect = sel.getRangeAt(0).getBoundingClientRect();
        setSelMenu({ x: rect.left, y: rect.bottom, text });
      } else {
        setSelMenu(null);
      }
    };
    document.addEventListener("mouseup", onUp);
    return () => document.removeEventListener("mouseup", onUp);
  }, []);

  async function saveAdd() {
    if (!addForm) return;
    const meanings = addForm.meanings.split(",").map((s) => s.trim()).filter(Boolean);
    if (!addForm.term.trim() || !meanings.length) { setMsg("Enter a term and at least one meaning."); return; }
    try {
      await axios.post("/api/v1/glossary/bulk", {
        terms: [{ te_term: addForm.term.trim(), meanings, category: addForm.category }],
      });
      setAddForm(null);
    } catch (e) { setMsg(errMsg(e)); }
  }

  const input: React.CSSProperties = {
    padding: "7px 10px", borderRadius: 8, border: "1px solid var(--warm-200)",
    fontSize: 13, outline: "none", width: "100%", background: "var(--white)",
  };

  return (
    <>
      <button onClick={generate}
        style={{ padding: "8px 14px", borderRadius: 9, border: "1px solid var(--rose-border)", background: "var(--rose-light)", color: "var(--rose-dark)", fontSize: 13, fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap" }}>
        ✨ Generate glossary
      </button>

      {/* ── Candidates panel ── */}
      <FloatingMenu open={genOpen} onClose={() => setGenOpen(false)} width={560} closeOnScroll={false}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
          <strong style={{ fontSize: 15, color: "var(--ink)" }}>Glossary candidates</strong>
          <button onClick={() => setGenOpen(false)} style={{ border: "none", background: "none", fontSize: 18, cursor: "pointer", color: "var(--ink-3)" }}>×</button>
        </div>
        {loading && <p style={{ fontSize: 13, color: "var(--ink-3)", padding: "24px 0", textAlign: "center" }}>Extracting terms (LLM + heuristics)…</p>}
        {!loading && cands.length > 0 && (
          <>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {cands.map((c, i) => (
                <div key={c.te_term} style={{ display: "flex", gap: 8, alignItems: "flex-start", padding: 8, borderRadius: 8, background: c.selected ? "var(--rose-light)" : "var(--cream)", border: "1px solid var(--warm-100)" }}>
                  <input type="checkbox" checked={c.selected} onChange={(e) => patch(i, { selected: e.target.checked })} style={{ marginTop: 6, cursor: "pointer" }} />
                  <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span style={{ fontFamily: "'Noto Sans Telugu', sans-serif", fontSize: 15, fontWeight: 600, color: "var(--ink)" }}>{c.te_term}</span>
                      {c.sources.map((s) => <span key={s} style={{ fontSize: 9, color: "var(--ink-3)", border: "1px solid var(--warm-200)", borderRadius: 10, padding: "1px 6px", textTransform: "uppercase", letterSpacing: "0.04em" }}>{s}</span>)}
                    </div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      <input value={c.meaningsStr} onChange={(e) => patch(i, { meaningsStr: e.target.value })}
                        placeholder="meaning 1, meaning 2, …" style={{ ...input, flex: "1 1 240px" }} />
                      <select value={c.category} onChange={(e) => patch(i, { category: e.target.value })}
                        style={{ ...input, width: "auto", flex: "0 0 auto" }}>
                        {CATS.map((cat) => <option key={cat} value={cat}>{cat}</option>)}
                      </select>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
              <button onClick={saveSelected}
                style={{ padding: "9px 18px", borderRadius: 9, border: "none", background: "var(--ink)", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
                Save selected ({cands.filter((c) => c.selected).length})
              </button>
              {msg && <span style={{ fontSize: 12, color: msg.startsWith("Saved") ? "var(--green)" : "var(--red)" }}>{msg}</span>}
            </div>
          </>
        )}
        {!loading && cands.length === 0 && msg && <p style={{ fontSize: 13, color: "var(--red)", padding: "16px 0" }}>{msg}</p>}
      </FloatingMenu>

      {/* ── Selection quick-add menu ── */}
      <FloatingMenu open={!!selMenu} onClose={() => setSelMenu(null)} anchor={selMenu} width={220}>
        <button onClick={() => { if (selMenu) setAddForm({ term: selMenu.text, meanings: "", category: "general" }); setSelMenu(null); }}
          style={{ width: "100%", padding: "8px 10px", borderRadius: 8, border: "none", background: "transparent", textAlign: "left", cursor: "pointer", fontSize: 13, color: "var(--ink)" }}>
          ⬡ Add “<span style={{ fontFamily: "'Noto Sans Telugu', sans-serif" }}>{selMenu?.text}</span>” to glossary
        </button>
      </FloatingMenu>

      {/* ── Quick add form ── */}
      <FloatingMenu open={!!addForm} onClose={() => setAddForm(null)} width={380} closeOnScroll={false}>
        {addForm && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <strong style={{ fontSize: 14, color: "var(--ink)" }}>Add glossary term</strong>
            <div>
              <label style={{ fontSize: 11, color: "var(--ink-3)" }}>Telugu term</label>
              <input value={addForm.term} onChange={(e) => setAddForm({ ...addForm, term: e.target.value })}
                style={{ ...input, fontFamily: "'Noto Sans Telugu', sans-serif", marginTop: 3 }} />
            </div>
            <div>
              <label style={{ fontSize: 11, color: "var(--ink-3)" }}>English meanings (comma-separated)</label>
              <input value={addForm.meanings} onChange={(e) => setAddForm({ ...addForm, meanings: e.target.value })}
                placeholder="Lord, Master" style={{ ...input, marginTop: 3 }} autoFocus />
            </div>
            <div>
              <label style={{ fontSize: 11, color: "var(--ink-3)" }}>Category</label>
              <select value={addForm.category} onChange={(e) => setAddForm({ ...addForm, category: e.target.value })} style={{ ...input, marginTop: 3 }}>
                {CATS.map((cat) => <option key={cat} value={cat}>{cat}</option>)}
              </select>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
              <button onClick={saveAdd} style={{ flex: 1, padding: "9px", borderRadius: 9, border: "none", background: "var(--ink)", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Save</button>
              <button onClick={() => setAddForm(null)} style={{ padding: "9px 14px", borderRadius: 9, border: "1px solid var(--warm-200)", background: "var(--white)", fontSize: 13, cursor: "pointer" }}>Cancel</button>
            </div>
          </div>
        )}
      </FloatingMenu>
    </>
  );
}
