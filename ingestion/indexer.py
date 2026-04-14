"""
Chroma indexer (local dev) and Pinecone indexer (demo/prod).

Indexed collection name: rbi_circulars
Embedding model: text-embedding-3-small (OpenAI, 1536 dims)
"""

import os
from pathlib import Path

import structlog
from langchain.schema import Document
from langchain_openai import OpenAIEmbeddings

logger = structlog.get_logger(__name__)

COLLECTION_NAME = "rbi_circulars"
EMBEDDING_MODEL = "text-embedding-3-small"


def _embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=os.environ["OPENAI_API_KEY"],
    )


def get_chroma_store(persist_dir: str | None = None):
    """Return a Chroma vectorstore for local dev."""
    from langchain_chroma import Chroma

    directory = persist_dir or os.environ.get("CHROMA_PERSIST_DIR", "./data/chroma")
    Path(directory).mkdir(parents=True, exist_ok=True)

    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=_embeddings(),
        persist_directory=directory,
        collection_metadata={"hnsw:space": "cosine"},
    )


def get_pinecone_store():
    """Return a Pinecone vectorstore for demo/prod."""
    from langchain_community.vectorstores import Pinecone as LangchainPinecone
    from pinecone import Pinecone

    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index_name = os.environ.get("PINECONE_INDEX_NAME", COLLECTION_NAME)
    index = pc.Index(index_name)

    return LangchainPinecone(
        index=index,
        embedding=_embeddings(),
        text_key="page_content",
    )


def get_indexed_circular_ids(store=None) -> set[str]:
    """
    Return the set of circular_ids already present in the collection.

    Used by the pipeline to skip re-indexing circulars that were already
    processed in a previous run (prevents duplicate chunks on reruns).
    """
    target_store = store or get_chroma_store()
    try:
        result = target_store._collection.get(include=["metadatas"])
        ids: set[str] = set()
        for meta in result.get("metadatas", []):
            cid = meta.get("circular_id")
            if cid:
                ids.add(cid)
        logger.info("existing_circular_ids_fetched", count=len(ids))
        return ids
    except Exception as exc:
        logger.warning("get_indexed_ids_failed", error=str(exc))
        return set()


_RETRY_ATTEMPTS = 4
_RETRY_BACKOFF_BASE = 60  # seconds — free tier is 100 RPM, so 60s clears the window


def index_documents(
    documents: list[Document],
    store=None,
    batch_size: int = 100,
) -> int:
    """
    Add documents to the vectorstore in batches with retry on 429 rate limits.

    Returns the count of successfully indexed documents.
    Uses Chroma (local) by default; pass a Pinecone store for prod.
    """
    import time

    if not documents:
        logger.warning("no_documents_to_index")
        return 0

    target_store = store or get_chroma_store()
    indexed = 0

    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                target_store.add_documents(batch)
                indexed += len(batch)
                logger.info(
                    "batch_indexed",
                    batch_start=i,
                    batch_size=len(batch),
                    total_so_far=indexed,
                )
                break
            except Exception as exc:
                err_str = str(exc)
                is_rate_limit = "429" in err_str or "quota" in err_str.lower()
                if is_rate_limit and attempt < _RETRY_ATTEMPTS:
                    wait = _RETRY_BACKOFF_BASE * attempt
                    logger.warning(
                        "rate_limit_backoff",
                        batch_start=i,
                        attempt=attempt,
                        wait_seconds=wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "batch_index_failed",
                        batch_start=i,
                        batch_size=len(batch),
                        attempt=attempt,
                        error=err_str,
                    )
                    break

    logger.info("indexing_complete", indexed=indexed, total=len(documents))
    return indexed
