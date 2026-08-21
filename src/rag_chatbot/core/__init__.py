"""Core RAG pipeline components.
This is about organizing the core components of the RAG pipeline into a package.
The RAG pipeline typically consists of the following components:
1. Retriever: Responsible for retrieving relevant documents or passages from a
   knowledge base or corpus based on the input query.
2. Generator: Responsible for generating responses based on the retrieved documents
   and the input query. This is often done using a language model.
3. RAG Pipeline: The main orchestrator that combines the retriever and generator to
   produce the final response.
4. Utilities: Helper functions and classes that support the retriever and generator,
   such as tokenization, embedding, and scoring functions.
"""

from rag_chatbot.configs import Settings, get_settings
from rag_chatbot.orchestrator import RAGOrchestrator

__all__ = ["RAGOrchestrator", "Settings", "get_settings"]
