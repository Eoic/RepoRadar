export interface SearchRequest {
  repo_url: string
  weight_purpose: number
  weight_stack: number
  limit: number
  min_stars: number
}

export interface SearchResultItem {
  full_name: string
  url: string
  description: string | null
  topics: string[]
  language_primary: string | null
  stars: number
  similarity_score: number
  purpose_score: number
  stack_score: number
}

export interface SearchResponse {
  query_repo: { full_name: string; description?: string }
  results: SearchResultItem[]
  indexed_count: number
  search_time_ms: number
}

export interface HealthResponse {
  status: string
  indexed_repos: number
  qdrant_connected: boolean
  github_rate_limit_remaining: number | null
}
