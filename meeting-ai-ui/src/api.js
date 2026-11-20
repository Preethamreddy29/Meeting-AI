import axios from "axios"

const configuredBase = (import.meta.env.VITE_API_URL || "").trim().replace(/\/+$/, "")
const browserBase = `${window.location.protocol}//${window.location.hostname}:8000`

export const API_BASE_URL = configuredBase || browserBase

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { Accept: "application/json" },
})

export function apiUrl(path) {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`
}

export function requestError(error, fallback = "Request failed") {
  const detail = error.response?.data?.detail
  if (Array.isArray(detail)) return detail.map((entry) => entry.msg).join("; ")
  return detail || error.response?.data?.error || error.message || fallback
}
