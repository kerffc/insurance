import React, { useState, useEffect } from "react";
import { api, TOKEN_KEY, USERNAME_KEY, getErrorDetail } from "./api";
import { Client, PolicyChange, Session, View } from "./types";
import LoginForm from "./components/LoginForm";
import UploadView from "./components/UploadView";
import PolicyChangeForm from "./components/PolicyChangeForm";
import MatchResultsView from "./components/MatchResultsView";
import MessageReviewView from "./components/MessageReviewView";
import DashboardView from "./components/DashboardView";

export default function App() {
  const [username, setUsername] = useState<string | null>(localStorage.getItem(USERNAME_KEY));
  const [view, setView] = useState<View>("upload");

  // Workflow state
  const [clients, setClients] = useState<Client[]>([]);
  const [selectedChange, setSelectedChange] = useState<PolicyChange | null>(null);
  const [matchedClients, setMatchedClients] = useState<Client[]>([]);
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  const handleLogout = () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USERNAME_KEY);
    setUsername(null);
  };

  const handleClientsUploaded = (uploaded: Client[]) => {
    setClients(uploaded);
    setView("policy-change");
  };

  const handleSelectChange = async (change: PolicyChange) => {
    setSelectedChange(change);
    setError("");
    if (clients.length === 0) {
      setError("Upload clients first before matching.");
      return;
    }
    try {
      const res = await api.post("/api/match", {
        clients,
        policy_change_id: change.id,
      });
      setMatchedClients(res.data.matched_clients);
      setView("review");
    } catch (err) {
      setError(getErrorDetail(err));
    }
  };

  const handleGenerate = async () => {
    if (!selectedChange || matchedClients.length === 0) return;
    setGenerating(true);
    setError("");
    try {
      // Build channel map: prefer whatsapp > phone (sms) > email
      const channelMap: Record<string, string> = {};
      for (const c of matchedClients) {
        if (c.whatsapp) channelMap[c.id] = "whatsapp";
        else if (c.phone) channelMap[c.id] = "sms";
        else if (c.email) channelMap[c.id] = "email";
        else channelMap[c.id] = "whatsapp";
      }
      const res = await api.post("/api/generate-messages", {
        clients: matchedClients,
        policy_change_id: selectedChange.id,
        channel_map: channelMap,
        agent_name: username || "Agent",
      });
      setCurrentSession(res.data);
    } catch (err) {
      setError(getErrorDetail(err));
    } finally {
      setGenerating(false);
    }
  };

  const handleViewSession = async (sessionId: string) => {
    try {
      const res = await api.get(`/api/sessions/${sessionId}`);
      setCurrentSession(res.data);
      setView("review");
    } catch (err) {
      setError(getErrorDetail(err));
    }
  };

  if (!username) {
    return <LoginForm onLogin={(u) => setUsername(u)} />;
  }

  return (
    <div style={{ fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" }}>
      {/* Header */}
      <div style={{ background: "#1a237e", color: "white", padding: "12px 24px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>Insurance Update Automation</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 13 }}>{username}</span>
          <button onClick={handleLogout} style={{ background: "rgba(255,255,255,0.2)", color: "white", border: "none", padding: "4px 12px", borderRadius: 4, cursor: "pointer" }}>
            Logout
          </button>
        </div>
      </div>

      {/* Nav tabs */}
      <div style={{ borderBottom: "1px solid #ddd", padding: "0 24px", display: "flex", gap: 0 }}>
        {(["upload", "policy-change", "review", "dashboard"] as View[]).map((v) => (
          <button
            key={v}
            onClick={() => { setView(v); setCurrentSession(null); setError(""); }}
            style={{
              padding: "12px 20px",
              border: "none",
              background: "none",
              borderBottom: view === v ? "3px solid #1a237e" : "3px solid transparent",
              fontWeight: view === v ? 700 : 400,
              cursor: "pointer",
              fontSize: 14,
            }}
          >
            {v === "upload" ? "Upload Clients" : v === "policy-change" ? "Policy Changes" : v === "review" ? "Review" : "Dashboard"}
          </button>
        ))}
        {clients.length > 0 && (
          <span style={{ marginLeft: "auto", alignSelf: "center", fontSize: 12, color: "#888" }}>
            {clients.length} clients loaded
          </span>
        )}
      </div>

      {/* Content */}
      <div style={{ maxWidth: 900, margin: "0 auto", padding: 24 }}>
        {error && <p style={{ color: "red", marginBottom: 12 }}>{error}</p>}

        {view === "upload" && (
          <UploadView onClientsUploaded={handleClientsUploaded} />
        )}

        {view === "policy-change" && (
          <PolicyChangeForm onSelectChange={handleSelectChange} />
        )}

        {view === "review" && !currentSession && matchedClients.length > 0 && selectedChange && (
          <div>
            <MatchResultsView
              clients={clients}
              matchedClients={matchedClients}
              policyChange={selectedChange}
              onProceedToGenerate={handleGenerate}
            />
            {generating && <p style={{ marginTop: 12 }}>Generating messages with Claude... This may take a moment.</p>}
          </div>
        )}

        {view === "review" && currentSession && (
          <MessageReviewView
            session={currentSession}
            onSessionUpdate={setCurrentSession}
          />
        )}

        {view === "review" && !currentSession && matchedClients.length === 0 && (
          <p>Upload clients and select a policy change to see matching results here.</p>
        )}

        {view === "dashboard" && (
          <DashboardView onViewSession={handleViewSession} />
        )}
      </div>
    </div>
  );
}
