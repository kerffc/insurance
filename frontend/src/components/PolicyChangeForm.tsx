import React, { useEffect, useState } from "react";
import { api, getErrorDetail } from "../api";
import { PolicyChange } from "../types";

const INSURERS = [
  "AIA", "Prudential", "Great Eastern", "NTUC Income", "Manulife",
  "AXA", "Tokio Marine", "FWD", "Aviva", "Etiqa", "HSBC Life",
  "Singlife", "China Life", "Raffles Health Insurance",
];

const POLICY_TYPES = [
  "All", "Life", "Health/Medical", "Motor", "Travel", "Home",
  "Critical Illness", "Investment-Linked (ILP)", "Personal Accident",
  "Disability Income", "Group Insurance",
];

interface Props {
  onSelectChange: (change: PolicyChange) => void;
}

export default function PolicyChangeForm({ onSelectChange }: Props) {
  const [changes, setChanges] = useState<PolicyChange[]>([]);
  const [insurer, setInsurer] = useState(INSURERS[0]);
  const [productLine, setProductLine] = useState(POLICY_TYPES[0]);
  const [planNames, setPlanNames] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [impact, setImpact] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/api/policy-changes").then((r) => setChanges(r.data)).catch(() => {});
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !description.trim() || !effectiveDate || !impact.trim()) {
      setError("Please fill in all required fields.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const res = await api.post("/api/policy-changes", {
        insurer,
        product_line: productLine,
        plan_names: planNames.split(",").map((s) => s.trim()).filter(Boolean),
        change_title: title,
        change_description: description,
        effective_date: effectiveDate,
        impact_summary: impact,
        source_url: sourceUrl || undefined,
      });
      setChanges([res.data, ...changes]);
      onSelectChange(res.data);
    } catch (err) {
      setError(getErrorDetail(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h3>Policy Change</h3>

      {changes.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h4>Existing Changes</h4>
          {changes.map((c) => (
            <div
              key={c.id}
              style={{ border: "1px solid #ddd", borderRadius: 4, padding: 12, marginBottom: 8, cursor: "pointer" }}
              onClick={() => onSelectChange(c)}
            >
              <strong>{c.change_title}</strong> — {c.insurer} ({c.product_line})
              <br />
              <span style={{ fontSize: 12, color: "#888" }}>Effective: {c.effective_date}</span>
            </div>
          ))}
        </div>
      )}

      <h4>Create New Change</h4>
      <form onSubmit={handleCreate}>
        <div style={row}>
          <label style={label}>Insurer *</label>
          <select value={insurer} onChange={(e) => setInsurer(e.target.value)} style={input}>
            {INSURERS.map((i) => <option key={i}>{i}</option>)}
          </select>
        </div>
        <div style={row}>
          <label style={label}>Product Line *</label>
          <select value={productLine} onChange={(e) => setProductLine(e.target.value)} style={input}>
            {POLICY_TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
        <div style={row}>
          <label style={label}>Specific Plans (comma-separated, optional)</label>
          <input value={planNames} onChange={(e) => setPlanNames(e.target.value)} style={input} placeholder="e.g. HealthShield Gold, Shield Plan A" />
        </div>
        <div style={row}>
          <label style={label}>Change Title *</label>
          <input value={title} onChange={(e) => setTitle(e.target.value)} style={input} placeholder="e.g. Panel hospital removal" />
        </div>
        <div style={row}>
          <label style={label}>Description *</label>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} style={{ ...input, minHeight: 80 }} placeholder="Detailed description of what changed..." />
        </div>
        <div style={row}>
          <label style={label}>Effective Date *</label>
          <input type="date" value={effectiveDate} onChange={(e) => setEffectiveDate(e.target.value)} style={input} />
        </div>
        <div style={row}>
          <label style={label}>Impact Summary *</label>
          <textarea value={impact} onChange={(e) => setImpact(e.target.value)} style={{ ...input, minHeight: 60 }} placeholder="How this affects policyholders..." />
        </div>
        <div style={row}>
          <label style={label}>Source URL (optional)</label>
          <input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} style={input} placeholder="Link to insurer circular" />
        </div>
        {error && <p style={{ color: "red" }}>{error}</p>}
        <button type="submit" disabled={loading} style={{ padding: "10px 24px", background: "#2196F3", color: "white", border: "none", borderRadius: 4, cursor: "pointer" }}>
          {loading ? "Saving..." : "Save & Match Clients"}
        </button>
      </form>
    </div>
  );
}

const row: React.CSSProperties = { marginBottom: 12 };
const label: React.CSSProperties = { display: "block", fontWeight: 600, marginBottom: 4, fontSize: 13 };
const input: React.CSSProperties = { width: "100%", padding: 8, boxSizing: "border-box", borderRadius: 4, border: "1px solid #ccc" };
