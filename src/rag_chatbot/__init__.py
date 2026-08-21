"""RAG Chatbot - Retrieval Augmented Generation Chatbot."""

__version__ = "0.1.0"


def main() -> None:
    """Launch the REST API with uvicorn."""
    import uvicorn

    from rag_chatbot.configs import get_settings

    settings = get_settings()
    uvicorn.run(
        "rag_chatbot.api.app:create_app",
        factory=True,
        host=settings.api.host,
        port=settings.api.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
