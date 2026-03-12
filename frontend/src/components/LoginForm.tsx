import React, { useState } from "react";
import { api, TOKEN_KEY, USERNAME_KEY, getErrorDetail } from "../api";

interface Props {
  onLogin: (username: string) => void;
}

export default function LoginForm({ onLogin }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setInfo("");
    setLoading(true);
    try {
      const endpoint = isRegister ? "/api/auth/register" : "/api/auth/login";
      const res = await api.post(endpoint, { username, password });
      if (res.data.token) {
        localStorage.setItem(TOKEN_KEY, res.data.token);
        localStorage.setItem(USERNAME_KEY, res.data.username);
        onLogin(res.data.username);
      } else {
        setInfo(res.data.message || "Registration submitted.");
      }
    } catch (err: any) {
      const detail = getErrorDetail(err);
      if (detail === "PENDING_APPROVAL") {
        setError("Your account is pending admin approval.");
      } else {
        setError(detail);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 400, margin: "100px auto", padding: 24 }}>
      <h2>Insurance Update Automation</h2>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 12 }}>
          <input
            type="text"
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            style={{ width: "100%", padding: 8, boxSizing: "border-box" }}
          />
        </div>
        <div style={{ marginBottom: 12 }}>
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ width: "100%", padding: 8, boxSizing: "border-box" }}
          />
        </div>
        <button type="submit" disabled={loading} style={{ padding: "8px 24px", marginRight: 8 }}>
          {loading ? "..." : isRegister ? "Register" : "Login"}
        </button>
        <button type="button" onClick={() => { setIsRegister(!isRegister); setError(""); setInfo(""); }}>
          {isRegister ? "Back to Login" : "Register"}
        </button>
      </form>
      {error && <p style={{ color: "red", marginTop: 12 }}>{error}</p>}
      {info && <p style={{ color: "green", marginTop: 12 }}>{info}</p>}
    </div>
  );
}
