import logging
import os
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


class RagService:
    """Lightweight RAG service backed by Chroma vector store."""

    def __init__(
        self,
        rag_dir: Path,
        collection_name: str = "incident_postmortem_rag",
        chunk_size: int = 900,
        chunk_overlap: int = 120,
    ) -> None:
        self.rag_dir = rag_dir
        self.collection_name = collection_name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._vector_store: Chroma | None = None
        self._initialized = False

    def _initialize(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        if not self.rag_dir.exists():
            logger.warning("RAG directory not found: %s", self.rag_dir)
            return

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY missing, RAG retrieval disabled.")
            return

        loader = DirectoryLoader(
            str(self.rag_dir),
            glob="*.txt",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
            show_progress=False,
        )
        documents = loader.load()
        if not documents:
            logger.warning("No RAG documents found in %s", self.rag_dir)
            return

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        chunks = splitter.split_documents(documents)
        if not chunks:
            logger.warning("No chunks generated from RAG documents.")
            return

        embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        embeddings = OpenAIEmbeddings(model=embedding_model, api_key=api_key)
        self._vector_store = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            collection_name=self.collection_name,
        )
        logger.info(
            "RAG initialized with docs=%s chunks=%s model=%s",
            len(documents),
            len(chunks),
            embedding_model,
        )

    def retrieve(self, query: str, top_k: int = 3, max_chars: int = 1800) -> str:
        try:
            self._initialize()
        except Exception as exc:
            logger.exception("Failed to initialize RAG service: %s", exc)
            return "No RAG context available."

        if self._vector_store is None:
            return "No RAG context available."

        retrieval_query = query.strip() or "incident timeline deployment error memory root cause"
        docs = self._vector_store.similarity_search(retrieval_query, k=max(1, top_k))
        if not docs:
            return "No RAG context available."

        context_parts: list[str] = []
        for doc in docs:
            source = Path(str(doc.metadata.get("source", "unknown"))).name
            text = " ".join(doc.page_content.split())
            context_parts.append(f"[{source}]\n{text}")

        context = "\n\n".join(context_parts)
        if len(context) > max_chars:
            context = context[:max_chars].rsplit(" ", 1)[0] + "..."

        logger.info(
            "RAG retrieve query_len=%s docs=%s context_chars=%s",
            len(retrieval_query),
            len(docs),
            len(context),
        )
        return context
