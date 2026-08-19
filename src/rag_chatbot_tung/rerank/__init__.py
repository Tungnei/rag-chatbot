"""Reranking implementations.

Only the no-op is imported eagerly. CrossEncoderReranker is reached through
`providers.build_reranker`, which imports the module lazily so that importing this
package never pulls in torch.
"""

from rag_chatbot_tung.rerank.noop import NoopReranker

__all__ = ["NoopReranker"]
