import logging

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""
    github_pat: str = ""

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str = ""
    qdrant_url: str = ""

    # Embedding
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_device: str = "cpu"

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "https://eoic.github.io"]
    session_secret: str = "change-me"

    # Indexing
    index_stale_days: int = 7
    seed_min_stars: int = 50

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

if settings.session_secret == "change-me":
    logger.warning("SESSION_SECRET is set to the default value. Set a strong secret in production.")
