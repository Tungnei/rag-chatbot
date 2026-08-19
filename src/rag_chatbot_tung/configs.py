"""Application configuration loaded from configs/default.yaml and environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    # Anthropic serves no embeddings API, so this half of the pipeline is configured
    # independently of the LLM and cannot follow it to every provider.
    provider: Literal["openai"] = "openai"
    model: str = "text-embedding-3-small"
    # Empty means the provider's own endpoint; set it to route through a gateway.
    base_url: str = ""
    batch_size: int = 100
    max_retries: int = 3


class LLMSettings(BaseModel):
    provider: Literal["openai", "anthropic"] = "openai"
    model: str = "gpt-4o-mini"
    # Empty means the provider's own endpoint. Point it at a gateway that speaks the
    # selected provider's protocol (e.g. a local proxy serving the Messages API).
    base_url: str = ""
    # OpenAI only. Current Claude models reject temperature with a 400, so the
    # Anthropic adapter never sends it — use `effort` there instead.
    temperature: float = 0.7
    # On Claude models that think, this caps thinking *and* answer together — leave
    # room or the answer gets cut off mid-sentence.
    max_tokens: int = 2000
    timeout: int = 60
    context_token_budget: int = 6000
    # History shares context_token_budget with the retrieved passages. Without a cap
    # of its own, three long turns starve the passages and the answer degrades even
    # when retrieval was perfect — which looks exactly like a retrieval bug.
    history_token_budget: int = 1500
    # Anthropic only, and not accepted by every model (Sonnet 4.5 errors on it), so it
    # is sent only when set.
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None


class RetrieverSettings(BaseModel):
    top_k: int = 3
    score_threshold: float = 0.3
    # Off by default so this can merge without changing production behaviour; turning
    # it back off is one variable rather than a revert.
    hybrid: bool = False
    dense_prefetch_limit: int = 30
    sparse_prefetch_limit: int = 30
    # Minimum BM25 score for a sparse-only hit to survive the post-fusion floor. None
    # means "keep only what the thresholded dense prefetch already vouched for" — a
    # hand-picked number here would be worse than no number at all.
    sparse_score_floor: float | None = None
    # How many fused candidates reach the reranker. Deliberately separate from
    # top_k, which means "chunks the LLM gets" and must keep meaning only that.
    fusion_limit: int = 30


class ChunkingSettings(BaseModel):
    chunk_size: int = 1000
    chunk_overlap: int = 100
    min_chunk_size: int = 50


class RerankSettings(BaseModel):
    # noop keeps the fusion order and costs nothing; cross_encoder needs the
    # `rerank` extra and a much larger image.
    provider: Literal["noop", "cross_encoder"] = "noop"
    model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    device: str = "cpu"
    top_n: int = 10


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
    anthropic_api_key: str = ""
    log_level: str = "INFO"

    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    embeddings: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    retriever: RetrieverSettings = Field(default_factory=RetrieverSettings)
    rerank: RerankSettings = Field(default_factory=RerankSettings)
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
