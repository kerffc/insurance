import React, { useEffect, useState } from "react";
import { api, getErrorDetail } from "../api";
import { SessionSummary } from "../types";

interface Props {
  onViewSession: (sessionId: string) => void;
}

export default function DashboardView({ onViewSession }: Props) {
  const [stats, setStats] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/api/dashboard/stats")
      .then((r) => setStats(r.data))
      .catch((err) => setError(getErrorDetail(err)));
  }, []);

  if (error) return <p style={{ color: "red" }}>{error}</p>;
  if (!stats) return <p>Loading dashboard...</p>;

  const sessions: SessionSummary[] = stats.sessions || [];

  return (
    <div>
      <h3>Dashboard</h3>

      <div style={{ display: "flex", gap: 16, marginBottom: 24 }}>
        <StatCard label="Total Sessions" value={stats.total_sessions} color="#2196F3" />
        <StatCard label="Total Notifications" value={stats.total_notifications} color="#9C27B0" />
        <StatCard label="Sent" value={stats.total_sent} color="#4CAF50" />
        <StatCard label="Pending" value={stats.total_pending} color="#FF9800" />
      </div>

      {sessions.length === 0 ? (
        <p>No sessions yet. Upload clients and generate messages to get started.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f0f0f0" }}>
              <th style={th}>Date</th>
              <th style={th}>Created By</th>
              <th style={th}>Clients</th>
              <th style={th}>Notifications</th>
              <th style={th}>Sent</th>
              <th style={th}>Progress</th>
              <th style={th}></th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => {
              const pct = s.total_notifications > 0 ? Math.round((s.sent_count / s.total_notifications) * 100) : 0;
              return (
                <tr key={s.id}>
                  <td style={td}>{new Date(s.created_at).toLocaleDateString()}</td>
                  <td style={td}>{s.created_by}</td>
                  <td style={td}>{s.total_clients}</td>
                  <td style={td}>{s.total_notifications}</td>
                  <td style={td}>{s.sent_count}</td>
                  <td style={td}>
                    <div style={{ background: "#e0e0e0", borderRadius: 4, height: 16, width: 120 }}>
                      <div style={{ background: "#4CAF50", borderRadius: 4, height: 16, width: `${pct}%`, minWidth: pct > 0 ? 8 : 0 }} />
                    </div>
                    <span style={{ fontSize: 11, color: "#888" }}>{pct}%</span>
                  </td>
                  <td style={td}>
                    <button onClick={() => onViewSession(s.id)} style={{ padding: "4px 12px", fontSize: 12, cursor: "pointer" }}>
                      View
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ background: "white", border: "1px solid #ddd", borderRadius: 8, padding: 16, minWidth: 120, textAlign: "center" }}>
      <div style={{ fontSize: 28, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 12, color: "#888" }}>{label}</div>
    </div>
  );
}

const th: React.CSSProperties = { padding: "8px 6px", textAlign: "left", borderBottom: "2px solid #ddd" };
const td: React.CSSProperties = { padding: "6px", borderBottom: "1px solid #eee" };
