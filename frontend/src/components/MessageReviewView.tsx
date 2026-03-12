import React, { useState } from "react";
import { api, getErrorDetail } from "../api";
import { Session, Notification } from "../types";

interface Props {
  session: Session;
  onSessionUpdate: (session: Session) => void;
}

export default function MessageReviewView({ session, onSessionUpdate }: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const notifications = session.notifications;
  const pendingCount = notifications.filter((n) => n.status === "pending").length;
  const reviewedCount = notifications.filter((n) => n.status === "reviewed").length;
  const sentCount = notifications.filter((n) => n.status === "sent").length;

  const updateNotif = async (notifId: string, update: { message?: string; status?: string }) => {
    try {
      const res = await api.patch(`/api/sessions/${session.id}/notifications/${notifId}`, update);
      const updated = { ...session, notifications: session.notifications.map((n) => n.id === notifId ? res.data : n) };
      onSessionUpdate(updated);
    } catch (err) {
      setError(getErrorDetail(err));
    }
  };

  const copyToClipboard = async (text: string, notifId: string) => {
    await navigator.clipboard.writeText(text);
    setCopiedId(notifId);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const bulkMarkSent = async () => {
    const reviewedIds = notifications.filter((n) => n.status === "reviewed").map((n) => n.id);
    if (reviewedIds.length === 0) return;
    try {
      await api.patch(`/api/sessions/${session.id}/notifications/bulk-status`, {
        notification_ids: reviewedIds,
        status: "sent",
      });
      const res = await api.get(`/api/sessions/${session.id}`);
      onSessionUpdate(res.data);
    } catch (err) {
      setError(getErrorDetail(err));
    }
  };

  return (
    <div>
      <h3>Review Messages</h3>
      <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
        <span style={{ background: "#fff3e0", padding: "4px 12px", borderRadius: 4 }}>Pending: {pendingCount}</span>
        <span style={{ background: "#e3f2fd", padding: "4px 12px", borderRadius: 4 }}>Reviewed: {reviewedCount}</span>
        <span style={{ background: "#e8f5e9", padding: "4px 12px", borderRadius: 4 }}>Sent: {sentCount}</span>
      </div>

      {reviewedCount > 0 && (
        <button onClick={bulkMarkSent} style={{ marginBottom: 16, padding: "8px 16px", background: "#FF9800", color: "white", border: "none", borderRadius: 4, cursor: "pointer" }}>
          Mark All Reviewed as Sent ({reviewedCount})
        </button>
      )}

      {error && <p style={{ color: "red" }}>{error}</p>}

      {notifications.map((n) => (
        <div key={n.id} style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16, marginBottom: 12, background: n.status === "sent" ? "#f9fff9" : "white" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <div>
              <strong>{n.client_name}</strong>
              <span style={{ marginLeft: 8, fontSize: 12, color: "#888" }}>
                via {n.channel} | {n.status}{n.edited ? " (edited)" : ""}
              </span>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              {n.status !== "sent" && (
                <>
                  <button
                    onClick={() => copyToClipboard(n.message, n.id)}
                    style={smallBtn}
                  >
                    {copiedId === n.id ? "Copied!" : "Copy"}
                  </button>
                  <button
                    onClick={() => { setEditingId(n.id); setEditText(n.message); }}
                    style={smallBtn}
                  >
                    Edit
                  </button>
                  {n.status === "pending" && (
                    <button onClick={() => updateNotif(n.id, { status: "reviewed" })} style={{ ...smallBtn, background: "#2196F3", color: "white" }}>
                      Mark Reviewed
                    </button>
                  )}
                  {n.status === "reviewed" && (
                    <button onClick={() => updateNotif(n.id, { status: "sent" })} style={{ ...smallBtn, background: "#4CAF50", color: "white" }}>
                      Mark Sent
                    </button>
                  )}
                </>
              )}
            </div>
          </div>

          {n.error && <p style={{ color: "red", fontSize: 12 }}>Error: {n.error}</p>}

          {editingId === n.id ? (
            <div>
              <textarea
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                style={{ width: "100%", minHeight: 120, padding: 8, boxSizing: "border-box", fontFamily: "inherit" }}
              />
              <div style={{ marginTop: 8 }}>
                <button onClick={() => { updateNotif(n.id, { message: editText }); setEditingId(null); }} style={{ ...smallBtn, background: "#4CAF50", color: "white" }}>Save</button>
                <button onClick={() => setEditingId(null)} style={{ ...smallBtn, marginLeft: 6 }}>Cancel</button>
              </div>
            </div>
          ) : (
            <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", background: "#f8f8f8", padding: 12, borderRadius: 4, margin: 0, fontSize: 13 }}>
              {n.message}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}

const smallBtn: React.CSSProperties = { padding: "4px 12px", border: "1px solid #ccc", borderRadius: 4, cursor: "pointer", fontSize: 12, background: "white" };
