"use client";
import { useState } from "react";
import useSWR from "swr";
import axios from "axios";
import { motion, AnimatePresence } from "motion/react";

interface GlossaryTerm {
  id: number;
  te_term: string;
  en_term: string;
  meanings: string[];
  category: string;
  notes: string | null;
}

const meaningsOf = (t: GlossaryTerm) => (t.meanings && t.meanings.length ? t.meanings : [t.en_term]);

const CATEGORIES = ["all", "theology", "name", "place", "general"] as const;
type Category = typeof CATEGORIES[number];

const CATEGORY_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  theology: { bg: "rgba(139,92,246,0.08)", border: "rgba(139,92,246,0.3)", text: "#7c3aed" },
  name:     { bg: "rgba(59,130,246,0.08)", border: "rgba(59,130,246,0.3)", text: "#1d4ed8" },
  place:    { bg: "rgba(16,185,129,0.08)", border: "rgba(16,185,129,0.3)", text: "#047857" },
  general:  { bg: "var(--gray-100)",       border: "var(--gray-200)",      text: "var(--gray-500)" },
};

const fetcher = (u: string) => axios.get(u).then(r => r.data);

function CategoryBadge({ category }: { category: string }) {
  const c = CATEGORY_COLORS[category] ?? CATEGORY_COLORS.general;
  return (
    <span style={{ fontSize: 10, fontWeight: 600, padding: "2px 8px", borderRadius: 99,
      background: c.bg, border: `1px solid ${c.border}`, color: c.text, textTransform: "uppercase", letterSpacing: "0.06em" }}>
      {category}
    </span>
  );
}

export default function GlossaryPage() {
  const { data: terms = [], isLoading, mutate } = useSWR<GlossaryTerm[]>("/api/v1/glossary", fetcher);

  const [filterCat, setFilterCat] = useState<Category>("all");
  const [search, setSearch] = useState("");

  // Add form
  const [addOpen, setAddOpen] = useState(false);
  const [newTe, setNewTe] = useState("");
  const [newEn, setNewEn] = useState("");
  const [newCat, setNewCat] = useState("theology");
  const [newNotes, setNewNotes] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Edit inline
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editEn, setEditEn] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [editCat, setEditCat] = useState("");
  const [saving, setSaving] = useState(false);

  // Delete confirm
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);

  const displayed = terms.filter(t => {
    const matchCat = filterCat === "all" || t.category === filterCat;
    const q = search.toLowerCase();
    const matchSearch = !q || t.te_term.toLowerCase().includes(q) || meaningsOf(t).join(" ").toLowerCase().includes(q);
    return matchCat && matchSearch;
  });

  async function addTerm() {
    const meanings = newEn.split(",").map(s => s.trim()).filter(Boolean);
    if (!newTe.trim() || !meanings.length) return;
    setAdding(true); setAddError(null);
    try {
      await axios.post("/api/v1/glossary", { te_term: newTe.trim(), meanings, category: newCat, notes: newNotes || null });
      mutate();
      setNewTe(""); setNewEn(""); setNewNotes(""); setAddOpen(false);
    } catch (e: unknown) {
      if (axios.isAxiosError(e)) setAddError(e.response?.data?.detail ?? e.message);
      else setAddError(String(e));
    } finally { setAdding(false); }
  }

  function startEdit(t: GlossaryTerm) {
    setEditingId(t.id); setEditEn(meaningsOf(t).join(", ")); setEditNotes(t.notes ?? ""); setEditCat(t.category);
  }

  async function saveEdit() {
    if (!editingId) return;
    const meanings = editEn.split(",").map(s => s.trim()).filter(Boolean);
    if (!meanings.length) return;
    setSaving(true);
    try {
      await axios.patch(`/api/v1/glossary/${editingId}`, { meanings, notes: editNotes || null, category: editCat });
      mutate();
      setEditingId(null);
    } catch (e) { console.error(e); }
    finally { setSaving(false); }
  }

  async function confirmDelete() {
    if (!deleteId) return;
    setDeleting(true);
    try {
      await axios.delete(`/api/v1/glossary/${deleteId}`);
      mutate();
      setDeleteId(null);
    } catch (e) { console.error(e); }
    finally { setDeleting(false); }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <h1 style={{ fontSize: 20, fontWeight: 600, color: "var(--gray-900)" }}>Glossary</h1>
          <p style={{ fontSize: 13, color: "var(--gray-400)", marginTop: 4 }}>
            Canonical translations for theological terms, names, and places. The editor will use these as hints.
          </p>
        </div>
        <motion.button onClick={() => setAddOpen(o => !o)} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
          style={{ padding: "8px 18px", borderRadius: 8, border: "none", background: "var(--rose)", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap" }}>
          + Add term
        </motion.button>
      </div>

      {/* Add form */}
      <AnimatePresence>
        {addOpen && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
            style={{ background: "var(--white)", border: "1px solid var(--rose-border)", borderRadius: 12, padding: "20px 24px", display: "flex", flexDirection: "column", gap: 14, overflow: "hidden" }}>
            <p style={{ fontSize: 13, fontWeight: 600, color: "var(--gray-900)" }}>Add new term</p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 10, alignItems: "start" }}>
              <div>
                <label style={{ fontSize: 11, color: "var(--gray-500)", display: "block", marginBottom: 4 }}>Telugu term *</label>
                <input value={newTe} onChange={e => setNewTe(e.target.value)}
                  placeholder="ప్రభువు"
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--gray-200)", fontSize: 14, fontFamily: "'Noto Sans Telugu', sans-serif", color: "var(--gray-900)", outline: "none" }} />
              </div>
              <div>
                <label style={{ fontSize: 11, color: "var(--gray-500)", display: "block", marginBottom: 4 }}>English meanings * (comma-separated)</label>
                <input value={newEn} onChange={e => setNewEn(e.target.value)}
                  placeholder="Lord, Master"
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--gray-200)", fontSize: 13, color: "var(--gray-900)", outline: "none" }} />
              </div>
              <div>
                <label style={{ fontSize: 11, color: "var(--gray-500)", display: "block", marginBottom: 4 }}>Category</label>
                <select value={newCat} onChange={e => setNewCat(e.target.value)}
                  style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid var(--gray-200)", fontSize: 12, color: "var(--gray-700)", background: "var(--white)", outline: "none" }}>
                  <option value="theology">Theology</option>
                  <option value="name">Name</option>
                  <option value="place">Place</option>
                  <option value="general">General</option>
                </select>
              </div>
            </div>
            <div>
              <label style={{ fontSize: 11, color: "var(--gray-500)", display: "block", marginBottom: 4 }}>Notes (optional)</label>
              <input value={newNotes} onChange={e => setNewNotes(e.target.value)}
                placeholder="Context or usage notes…"
                style={{ width: "100%", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--gray-200)", fontSize: 12, color: "var(--gray-700)", outline: "none" }} />
            </div>
            {addError && <p style={{ fontSize: 12, color: "var(--red)" }}>✗ {addError}</p>}
            <div style={{ display: "flex", gap: 8 }}>
              <motion.button onClick={addTerm} disabled={adding || !newTe.trim() || !newEn.trim()}
                whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }}
                style={{ padding: "8px 20px", borderRadius: 8, border: "none", background: "var(--rose)", color: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer", opacity: adding ? 0.5 : 1 }}>
                {adding ? "Adding…" : "Add term"}
              </motion.button>
              <button onClick={() => setAddOpen(false)}
                style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid var(--gray-200)", background: "var(--white)", color: "var(--gray-500)", fontSize: 12, cursor: "pointer" }}>
                Cancel
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Filter bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search terms…"
          style={{ padding: "7px 12px", borderRadius: 8, border: "1px solid var(--gray-200)", fontSize: 13, color: "var(--gray-700)", outline: "none", width: 200, background: "var(--white)" }} />
        <div style={{ display: "flex", gap: 4 }}>
          {CATEGORIES.map(cat => (
            <button key={cat} onClick={() => setFilterCat(cat)}
              style={{
                padding: "5px 12px", borderRadius: 7, border: "none", cursor: "pointer", fontSize: 11,
                fontWeight: filterCat === cat ? 600 : 400,
                background: filterCat === cat ? "var(--rose)" : "var(--gray-100)",
                color: filterCat === cat ? "#fff" : "var(--gray-500)",
              }}>
              {cat.charAt(0).toUpperCase() + cat.slice(1)}
            </button>
          ))}
        </div>
        <span style={{ fontSize: 12, color: "var(--gray-400)", marginLeft: "auto" }}>
          {displayed.length} term{displayed.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Terms table */}
      {isLoading && <p style={{ color: "var(--gray-400)", fontSize: 13, textAlign: "center", padding: "40px 0" }}>Loading glossary…</p>}

      {!isLoading && displayed.length === 0 && (
        <div style={{ background: "var(--gray-50)", border: "1px dashed var(--gray-300)", borderRadius: 12, padding: "48px 24px", textAlign: "center" }}>
          <p style={{ fontSize: 14, color: "var(--gray-500)" }}>
            {terms.length === 0 ? "No terms yet. Add one above." : "No matches for this filter."}
          </p>
        </div>
      )}

      {displayed.length > 0 && (
        <div className="scroll-x" style={{ background: "var(--white)", border: "1px solid var(--gray-200)", borderRadius: 12, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 620 }}>
            <thead>
              <tr style={{ background: "var(--gray-50)", borderBottom: "1px solid var(--gray-200)" }}>
                <th style={{ padding: "10px 16px", fontSize: 11, fontWeight: 600, color: "var(--gray-400)", textAlign: "left", textTransform: "uppercase", letterSpacing: "0.06em" }}>Telugu</th>
                <th style={{ padding: "10px 16px", fontSize: 11, fontWeight: 600, color: "var(--gray-400)", textAlign: "left", textTransform: "uppercase", letterSpacing: "0.06em" }}>English meanings</th>
                <th style={{ padding: "10px 16px", fontSize: 11, fontWeight: 600, color: "var(--gray-400)", textAlign: "left", textTransform: "uppercase", letterSpacing: "0.06em" }}>Category</th>
                <th style={{ padding: "10px 16px", fontSize: 11, fontWeight: 600, color: "var(--gray-400)", textAlign: "left", textTransform: "uppercase", letterSpacing: "0.06em" }}>Notes</th>
                <th style={{ padding: "10px 16px", width: 100 }}></th>
              </tr>
            </thead>
            <tbody>
              {displayed.map(term => (
                <tr key={term.id} style={{ borderBottom: "1px solid var(--gray-100)" }}>
                  <td style={{ padding: "12px 16px", verticalAlign: "top" }}>
                    <span style={{ fontFamily: "'Noto Sans Telugu', sans-serif", fontSize: 15, color: "var(--gray-900)", fontWeight: 500 }}>
                      {term.te_term}
                    </span>
                  </td>
                  <td style={{ padding: "12px 16px", verticalAlign: "top" }}>
                    {editingId === term.id ? (
                      <input value={editEn} onChange={e => setEditEn(e.target.value)}
                        placeholder="Lord, Master"
                        style={{ padding: "6px 10px", borderRadius: 7, border: "1px solid var(--rose-border)", fontSize: 13, color: "var(--gray-900)", outline: "none", width: "100%" }} />
                    ) : (
                      <span style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                        {meaningsOf(term).map((m, i) => (
                          <span key={i} style={{ fontSize: 12, color: i === 0 ? "var(--gray-900)" : "var(--gray-600)", fontWeight: i === 0 ? 600 : 400, background: "var(--gray-100)", borderRadius: 6, padding: "2px 8px" }}>{m}</span>
                        ))}
                      </span>
                    )}
                  </td>
                  <td style={{ padding: "12px 16px", verticalAlign: "top" }}>
                    {editingId === term.id ? (
                      <select value={editCat} onChange={e => setEditCat(e.target.value)}
                        style={{ padding: "5px 8px", borderRadius: 7, border: "1px solid var(--gray-200)", fontSize: 11, color: "var(--gray-700)", background: "var(--white)", outline: "none" }}>
                        <option value="theology">Theology</option>
                        <option value="name">Name</option>
                        <option value="place">Place</option>
                        <option value="general">General</option>
                      </select>
                    ) : (
                      <CategoryBadge category={term.category} />
                    )}
                  </td>
                  <td style={{ padding: "12px 16px", verticalAlign: "top" }}>
                    {editingId === term.id ? (
                      <input value={editNotes} onChange={e => setEditNotes(e.target.value)}
                        placeholder="Notes…"
                        style={{ padding: "6px 10px", borderRadius: 7, border: "1px solid var(--gray-200)", fontSize: 12, color: "var(--gray-700)", outline: "none", width: "100%" }} />
                    ) : (
                      <span style={{ fontSize: 12, color: "var(--gray-400)", fontStyle: term.notes ? "normal" : "italic" }}>
                        {term.notes || "—"}
                      </span>
                    )}
                  </td>
                  <td style={{ padding: "12px 16px", verticalAlign: "top" }}>
                    {editingId === term.id ? (
                      <div style={{ display: "flex", gap: 6 }}>
                        <button onClick={saveEdit} disabled={saving}
                          style={{ padding: "4px 10px", borderRadius: 6, border: "none", background: "var(--rose)", color: "#fff", fontSize: 11, fontWeight: 600, cursor: "pointer" }}>
                          {saving ? "…" : "Save"}
                        </button>
                        <button onClick={() => setEditingId(null)}
                          style={{ padding: "4px 8px", borderRadius: 6, border: "1px solid var(--gray-200)", background: "var(--white)", color: "var(--gray-500)", fontSize: 11, cursor: "pointer" }}>
                          ✕
                        </button>
                      </div>
                    ) : deleteId === term.id ? (
                      <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                        <span style={{ fontSize: 10, color: "var(--gray-500)" }}>Delete?</span>
                        <button onClick={confirmDelete} disabled={deleting}
                          style={{ padding: "3px 8px", borderRadius: 5, border: "none", background: "#ef4444", color: "#fff", fontSize: 10, fontWeight: 600, cursor: "pointer" }}>
                          {deleting ? "…" : "Yes"}
                        </button>
                        <button onClick={() => setDeleteId(null)}
                          style={{ padding: "3px 6px", borderRadius: 5, border: "1px solid var(--gray-200)", background: "var(--white)", color: "var(--gray-500)", fontSize: 10, cursor: "pointer" }}>
                          No
                        </button>
                      </div>
                    ) : (
                      <div style={{ display: "flex", gap: 6 }}>
                        <button onClick={() => startEdit(term)} title="Edit"
                          style={{ padding: "4px 10px", borderRadius: 6, border: "1px solid var(--gray-200)", background: "var(--white)", color: "var(--gray-500)", fontSize: 11, cursor: "pointer" }}>
                          Edit
                        </button>
                        <button onClick={() => setDeleteId(term.id)} title="Delete"
                          style={{ padding: "4px 8px", borderRadius: 6, border: "1px solid var(--gray-200)", background: "var(--white)", color: "var(--gray-400)", fontSize: 11, cursor: "pointer" }}>
                          🗑
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
