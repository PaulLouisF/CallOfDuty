import os
from functools import lru_cache

from pydantic import BaseModel


class Settings(BaseModel):
    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "password")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.mistral.ai/v1")
    llm_model: str = os.getenv("LLM_MODEL", "mistral-small-latest")
    api_cors_origins: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "API_CORS_ORIGINS",
            (
                "http://localhost:5173,http://127.0.0.1:5173,"
                "http://localhost:5174,http://127.0.0.1:5174"
            ),
        ).split(",")
        if origin.strip()
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
