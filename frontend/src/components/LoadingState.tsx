export function LoadingState() {
  return (
    <div className="loading-container" role="status" aria-live="polite">
      <span className="visually-hidden">Loading search results</span>
      <div className="loading-icon" aria-hidden="true">
        <span className="material-symbols-outlined">progress_activity</span>
      </div>
      <p className="loading-text">Searching repositories...</p>
      <p className="loading-subtext">Fetching metadata, analyzing code, generating embeddings...</p>
    </div>
  );
}
