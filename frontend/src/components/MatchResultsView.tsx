import React from "react";
import { Client, PolicyChange } from "../types";

interface Props {
  clients: Client[];
  matchedClients: Client[];
  policyChange: PolicyChange;
  onProceedToGenerate: () => void;
}

export default function MatchResultsView({ clients, matchedClients, policyChange, onProceedToGenerate }: Props) {
  return (
    <div>
      <h3>Matching Results</h3>
      <div style={{ background: "#e8f5e9", padding: 16, borderRadius: 8, marginBottom: 16 }}>
        <strong>{matchedClients.length}</strong> of {clients.length} clients affected by:
        <br />
        <strong>{policyChange.change_title}</strong> — {policyChange.insurer} ({policyChange.product_line})
      </div>

      {matchedClients.length === 0 ? (
        <p>No clients match this policy change. Check that your CSV has clients with the matching insurer and policy type.</p>
      ) : (
        <>
          <div style={{ overflowX: "auto", marginBottom: 16 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#f0f0f0" }}>
                  <th style={th}>Name</th>
                  <th style={th}>Insurer</th>
                  <th style={th}>Policy Type</th>
                  <th style={th}>Policy #</th>
                  <th style={th}>Plan</th>
                  <th style={th}>Contact</th>
                </tr>
              </thead>
              <tbody>
                {matchedClients.map((c) => (
                  <tr key={c.id}>
                    <td style={td}>{c.name}</td>
                    <td style={td}>{c.insurer}</td>
                    <td style={td}>{c.policy_type}</td>
                    <td style={td}>{c.policy_number}</td>
                    <td style={td}>{c.plan_name || "-"}</td>
                    <td style={td}>
                      {c.whatsapp ? `WA: ${c.whatsapp}` : c.phone ? `Tel: ${c.phone}` : c.email || "No contact"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            onClick={onProceedToGenerate}
            style={{ padding: "10px 24px", background: "#4CAF50", color: "white", border: "none", borderRadius: 4, cursor: "pointer", fontSize: 14 }}
          >
            Generate Messages for {matchedClients.length} Clients
          </button>
        </>
      )}
    </div>
  );
}

const th: React.CSSProperties = { padding: "8px 6px", textAlign: "left", borderBottom: "2px solid #ddd" };
const td: React.CSSProperties = { padding: "6px", borderBottom: "1px solid #eee" };
