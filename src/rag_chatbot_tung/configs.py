"""Application configuration loaded from configs/default.yaml and environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "default.yaml"


class QdrantSettings(BaseModel):
    url: str = "http://localhost:6333"
    api_key: str | None = None
    collection_name: str = "documents"
    vector_size: int = 1536
    distance: str = "Cosine"


class EmbeddingSettings(BaseModel):
    model: str = "text-embedding-3-small"
    batch_size: int = 100
    max_retries: int = 3


class LLMSettings(BaseModel):
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2000
    timeout: int = 60
    context_token_budget: int = 6000


class RetrieverSettings(BaseModel):
    top_k: int = 3
    score_threshold: float = 0.3


class ChunkingSettings(BaseModel):
    chunk_size: int = 1000
    chunk_overlap: int = 100
    min_chunk_size: int = 50


class APISettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


class StorageSettings(BaseModel):
    documents_dir: Path = PROJECT_ROOT / "data" / "documents"
    upload_dir: Path = PROJECT_ROOT / "data" / "uploads"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        yaml_file=DEFAULT_CONFIG_PATH,
        extra="ignore",
    )

    openai_api_key: str = ""
    log_level: str = "INFO"

    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    embeddings: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    retriever: RetrieverSettings = Field(default_factory=RetrieverSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    api: APISettings = Field(default_factory=APISettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Priority: constructor args > environment > .env > YAML > field defaults."""
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


@lru_cache
def get_settings(config_path: Path | None = None) -> Settings:
    if config_path is None:
        return Settings()

    class _Settings(Settings):
        model_config = SettingsConfigDict(**{**Settings.model_config, "yaml_file": config_path})

    return _Settings()
