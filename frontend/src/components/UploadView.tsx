import React, { useRef, useState } from "react";
import { api, getErrorDetail } from "../api";
import { Client } from "../types";

interface Props {
  onClientsUploaded: (clients: Client[]) => void;
}

export default function UploadView({ onClientsUploaded }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [clients, setClients] = useState<Client[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const handleFile = async (file: File) => {
    setLoading(true);
    setErrors([]);
    setWarnings([]);
    setClients([]);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await api.post("/api/upload-clients", form);
      setClients(res.data.clients);
      setErrors(res.data.errors || []);
      setWarnings(res.data.warnings || []);
    } catch (err: any) {
      const detail = getErrorDetail(err);
      setErrors([detail]);
    } finally {
      setLoading(false);
    }
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div>
      <h3>Upload Client CSV</h3>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => fileRef.current?.click()}
        style={{
          border: `2px dashed ${dragOver ? "#4CAF50" : "#ccc"}`,
          borderRadius: 8,
          padding: 40,
          textAlign: "center",
          cursor: "pointer",
          background: dragOver ? "#f0fff0" : "#fafafa",
          marginBottom: 16,
        }}
      >
        <p>{loading ? "Uploading..." : "Drag & drop a CSV file here, or click to select"}</p>
        <p style={{ fontSize: 12, color: "#888" }}>
          Required columns: Name, Insurer, Policy Type, Policy Number
        </p>
        <input ref={fileRef} type="file" accept=".csv" onChange={onFileChange} style={{ display: "none" }} />
      </div>

      {errors.length > 0 && (
        <div style={{ background: "#fff0f0", padding: 12, borderRadius: 4, marginBottom: 12 }}>
          {errors.map((e, i) => <p key={i} style={{ color: "red", margin: "4px 0" }}>{e}</p>)}
        </div>
      )}

      {warnings.length > 0 && (
        <div style={{ background: "#fffbe6", padding: 12, borderRadius: 4, marginBottom: 12 }}>
          {warnings.map((w, i) => <p key={i} style={{ color: "#b8860b", margin: "4px 0" }}>{w}</p>)}
        </div>
      )}

      {clients.length > 0 && (
        <>
          <p><strong>{clients.length}</strong> clients parsed successfully.</p>
          <div style={{ overflowX: "auto", marginBottom: 16 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#f0f0f0" }}>
                  <th style={th}>Name</th>
                  <th style={th}>Insurer</th>
                  <th style={th}>Policy Type</th>
                  <th style={th}>Policy #</th>
                  <th style={th}>Email</th>
                  <th style={th}>Phone</th>
                  <th style={th}>WhatsApp</th>
                </tr>
              </thead>
              <tbody>
                {clients.slice(0, 50).map((c) => (
                  <tr key={c.id}>
                    <td style={td}>{c.name}</td>
                    <td style={td}>{c.insurer}</td>
                    <td style={td}>{c.policy_type}</td>
                    <td style={td}>{c.policy_number}</td>
                    <td style={td}>{c.email || "-"}</td>
                    <td style={td}>{c.phone || "-"}</td>
                    <td style={td}>{c.whatsapp || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {clients.length > 50 && <p style={{ color: "#888" }}>Showing first 50 of {clients.length}</p>}
          </div>
          <button
            onClick={() => onClientsUploaded(clients)}
            style={{ padding: "10px 24px", background: "#4CAF50", color: "white", border: "none", borderRadius: 4, cursor: "pointer", fontSize: 14 }}
          >
            Confirm Upload ({clients.length} clients)
          </button>
        </>
      )}
    </div>
  );
}

const th: React.CSSProperties = { padding: "8px 6px", textAlign: "left", borderBottom: "2px solid #ddd" };
const td: React.CSSProperties = { padding: "6px", borderBottom: "1px solid #eee" };
