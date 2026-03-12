import axios, { AxiosError } from "axios";

export const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

export function getErrorDetail(err: unknown, fallback = "Something went wrong."): string {
  if (err instanceof AxiosError) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail?.errors) return detail.errors.join("; ");
    return err.response ? `HTTP ${err.response.status}` : fallback;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

export const TOKEN_KEY = "insurance-update-token";
export const USERNAME_KEY = "insurance-update-username";

export const api = axios.create({ baseURL: API_BASE });

api.interceptors.request.use((config) => {
  const t = localStorage.getItem(TOKEN_KEY);
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

api.interceptors.response.use(undefined, (err) => {
  if (err instanceof AxiosError && err.response?.status === 401) {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USERNAME_KEY);
    window.location.reload();
  }
  return Promise.reject(err);
});
