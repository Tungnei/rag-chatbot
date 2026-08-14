from __future__ import annotations

import yaml

from rag_chatbot_tung.configs import Settings, get_settings

# Isolation from a developer's .env is suite-wide — see the away_from_dotenv fixture
# in conftest.py.


def test_defaults_are_qdrant_based():
    s = Settings()
    assert s.qdrant.url.endswith(":6333")
    assert s.embeddings.model == "text-embedding-3-small"
    assert s.qdrant.vector_size == 1536


def test_yaml_values_populate_nested_sections(tmp_path):
    config = tmp_path / "custom.yaml"
    config.write_text(
        yaml.safe_dump({"retriever": {"top_k": 9}, "llm": {"model": "gpt-4o"}}),
        encoding="utf-8",
    )
    get_settings.cache_clear()
    s = get_settings(config)
    assert s.retriever.top_k == 9
    assert s.llm.model == "gpt-4o"
    get_settings.cache_clear()


def test_env_overrides_yaml(tmp_path, monkeypatch):
    config = tmp_path / "custom.yaml"
    config.write_text(yaml.safe_dump({"retriever": {"top_k": 9}}), encoding="utf-8")
    monkeypatch.setenv("RETRIEVER__TOP_K", "2")
    get_settings.cache_clear()
    assert get_settings(config).retriever.top_k == 2
    get_settings.cache_clear()
