import type { SearchResultItem } from "../types/api";
import { ResultCard } from "./ResultCard";

interface ResultsListProps {
  results: SearchResultItem[];
  indexedCount: number;
  searchTimeMs: number;
  queryRepo: string;
}

export function ResultsList({ results, indexedCount, searchTimeMs, queryRepo }: ResultsListProps) {
  const matchWord = results.length === 1 ? "match" : "matches";

  return (
    <section className="results-container" aria-labelledby="results-heading">
      <div className="results-header">
        <h2 id="results-heading" className="results-query">
          Showing results similar to <strong>{queryRepo}</strong>
        </h2>
        <span
          className="results-stats"
          aria-label={`${results.length} ${matchWord} found in ${searchTimeMs.toFixed(0)} milliseconds across ${indexedCount.toLocaleString()} indexed repositories`}
        >
          {results.length} {matchWord} · {searchTimeMs.toFixed(0)}ms · {indexedCount.toLocaleString()} repos indexed
        </span>
      </div>

      <ul className="results-list" role="list">
        {results.map((r, i) => (
          <li key={r.full_name}>
            <ResultCard result={r} rank={i} />
          </li>
        ))}
      </ul>

      {results.length === 0 && (
        <div className="no-results" role="status">
          <div className="no-results-icon" aria-hidden="true">
            <span className="material-symbols-outlined">search_off</span>
          </div>
          <p>No similar repositories found. Try indexing more repos first.</p>
        </div>
      )}
    </section>
  );
}
