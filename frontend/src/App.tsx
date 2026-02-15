import { useState, useEffect } from "react";
import { searchRepos, getHealth } from "./api/client";
import type { SearchResponse } from "./api/client";
import { useTheme } from "./hooks/useTheme";
import { ThemeToggle } from "./components/ThemeToggle";
import { SearchInput } from "./components/SearchInput";
import { WeightSliders } from "./components/WeightSliders";
import { ResultsList } from "./components/ResultsList";
import { LoadingState } from "./components/LoadingState";
import "./App.css";

function App() {
  const { theme, toggleTheme } = useTheme();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [purposeWeight, setPurposeWeight] = useState(0.7);
  const [indexedCount, setIndexedCount] = useState<number>(0);

  useEffect(() => {
    getHealth()
      .then((h) => setIndexedCount(h.indexed_repos))
      .catch(() => { });
  }, []);

  const handleSearch = async (url: string) => {
    setLoading(true);
    setError(null);
    setSearchResult(null);

    try {
      const result = await searchRepos({
        repo_url: url,
        weight_purpose: purposeWeight,
        weight_stack: Math.round((1 - purposeWeight) * 100) / 100,
        limit: 20,
        min_stars: 0,
      });
      setSearchResult(result);
      setIndexedCount(result.indexed_count);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <a href="#main-content" className="skip-link">Skip to main content</a>

      <header className="header">
        <ThemeToggle theme={theme} onToggle={toggleTheme} />
        <div className="logo-section">
          <span className="material-symbols-outlined logo-icon" aria-hidden="true">radar</span>
          <h1 className="logo-text">
            Repo<span className="logo-accent">Radar</span>
          </h1>
        </div>
        <p className="tagline">Discover similar repositories through semantic vector analysis</p>
      </header>

      <main id="main-content" className="main">
        <section className="search-section" aria-label="Search for repositories">
          <SearchInput onSearch={handleSearch} isLoading={loading} />
          <WeightSliders purposeWeight={purposeWeight} onWeightChange={setPurposeWeight} />
        </section>

        {loading && <LoadingState />}

        {error && (
          <div className="error-banner" role="alert" aria-live="assertive">
            <span className="error-icon" aria-hidden="true">
              <span className="material-symbols-outlined">error</span>
            </span>
            <span>{error}</span>
          </div>
        )}

        {searchResult && !loading && (
          <ResultsList
            results={searchResult.results}
            indexedCount={searchResult.indexed_count}
            searchTimeMs={searchResult.search_time_ms}
            queryRepo={searchResult.query_repo.full_name}
          />
        )}
      </main>

      <footer className="footer">
        <span>
          Scanning across{" "}
          <strong>{indexedCount.toLocaleString()}</strong> indexed repositories
        </span>
      </footer>
    </div>
  );
}

export default App;
