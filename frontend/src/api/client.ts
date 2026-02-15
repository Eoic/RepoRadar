export type { SearchRequest, SearchResultItem, SearchResponse, HealthResponse } from '../types/api'
import type { SearchRequest, SearchResponse, HealthResponse } from '../types/api'

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs = 30000): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(id);
  }
}

export async function searchRepos(params: SearchRequest): Promise<SearchResponse> {
  const res = await fetchWithTimeout(`${API_BASE}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Search failed" }));
    throw new Error(err.detail || "Search failed");
  }
  return res.json();
}

export async function indexRepo(repo_url: string): Promise<{ status: string; repo_id: number; full_name: string }> {
  const res = await fetchWithTimeout(`${API_BASE}/api/index`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_url }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Indexing failed" }));
    throw new Error(err.detail || "Indexing failed");
  }
  return res.json();
}

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetchWithTimeout(`${API_BASE}/api/health`);
  if (!res.ok) {
    throw new Error("Health check failed");
  }
  return res.json();
}

export function getGitHubAuthUrl(): string {
  return `${API_BASE}/api/auth/github`;
}
