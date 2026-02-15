import { useState, type FormEvent } from "react";

interface SearchInputProps {
  onSearch: (url: string) => void;
  isLoading: boolean;
}

export function SearchInput({ onSearch, isLoading }: SearchInputProps) {
  const [url, setUrl] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (url.trim()) onSearch(url.trim());
  };

  return (
    <form onSubmit={handleSubmit} className="search-form" role="search">
      <label htmlFor="repo-url" className="visually-hidden">Repository URL</label>
      <div className="search-input-wrapper">
        <span className="search-prefix" aria-hidden="true">
          <span className="material-symbols-outlined">search</span>
        </span>
        <input
          id="repo-url"
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="owner/repo or https://github.com/owner/repo"
          disabled={isLoading}
          className="search-input"
          aria-describedby="search-hint"
        />
        <span id="search-hint" className="visually-hidden">
          Enter a GitHub repository URL or owner/repo shorthand
        </span>
        <button
          type="submit"
          disabled={isLoading || !url.trim()}
          className="search-button"
          aria-label={isLoading ? "Searching repositories" : "Search for similar repositories"}
        >
          {isLoading ? "Searching..." : "Search"}
        </button>
      </div>
    </form>
  );
}
