import type { SearchResultItem } from "../types/api";

const LANG_COLORS: Record<string, string> = {
  Python: "#3572A5",
  JavaScript: "#f1e05a",
  TypeScript: "#3178c6",
  Rust: "#dea584",
  Go: "#00ADD8",
  Java: "#b07219",
  "C++": "#f34b7d",
  C: "#555555",
  Ruby: "#701516",
  Swift: "#F05138",
  Kotlin: "#A97BFF",
  Dart: "#00B4AB",
  PHP: "#4F5D95",
  Shell: "#89e051",
};

interface ResultCardProps {
  result: SearchResultItem;
  rank: number;
}

export function ResultCard({ result, rank }: ResultCardProps) {
  const langColor = LANG_COLORS[result.language_primary || ""] || "#888";
  const overallPct = Math.round(result.similarity_score * 100);
  const purposePct = Math.round(result.purpose_score * 100);
  const stackPct = Math.round(result.stack_score * 100);

  return (
    <a
      href={result.url}
      target="_blank"
      rel="noopener noreferrer"
      className="result-card"
      aria-label={`${result.full_name}, ${result.stars.toLocaleString()} stars, ${overallPct}% similar`}
    >
      <div className="result-header">
        <span className="result-rank" aria-hidden="true">#{rank + 1}</span>
        <span className="result-name">{result.full_name}</span>
        <span className="result-stars" aria-label={`${result.stars.toLocaleString()} stars`}>
          <span className="material-symbols-outlined filled" aria-hidden="true">star</span>
          {result.stars.toLocaleString()}
        </span>
      </div>

      {result.description && (
        <p className="result-description">{result.description}</p>
      )}

      <div className="result-meta">
        {result.language_primary && (
          <span className="result-lang">
            <span className="lang-dot" style={{ background: langColor }} aria-hidden="true" />
            {result.language_primary}
          </span>
        )}
        {result.topics.slice(0, 4).map((t) => (
          <span key={t} className="result-topic">{t}</span>
        ))}
      </div>

      <div className="result-scores">
        <ScoreBar label="Overall" score={result.similarity_score} pct={overallPct} color="var(--accent)" />
        <ScoreBar label="Purpose" score={result.purpose_score} pct={purposePct} color="var(--purpose)" />
        <ScoreBar label="Stack" score={result.stack_score} pct={stackPct} color="var(--stack)" />
      </div>
    </a>
  );
}

function ScoreBar({ label, score, pct, color }: { label: string; score: number; pct: number; color: string }) {
  return (
    <div className="score-bar-row">
      <span className="score-label">{label}</span>
      <div
        className="score-track"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label} score: ${pct}%`}
      >
        <div
          className="score-fill"
          style={{ width: `${score * 100}%`, background: color }}
        />
      </div>
      <span className="score-value">{pct}%</span>
    </div>
  );
}
