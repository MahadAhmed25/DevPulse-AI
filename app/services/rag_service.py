import structlog
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedding_service import EmbeddingService

logger = structlog.get_logger(__name__)

# Matches Titan Embeddings V2 output dimension
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


class RAGService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._embedder = EmbeddingService()
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", " ", ""],
        )

    async def index_file(self, repository_id: str, file_path: str, content: str) -> int:
        """Chunk a file, embed each chunk, and upsert into pgvector.
        Returns the number of chunks stored."""
        chunks = self._splitter.split_text(content)
        if not chunks:
            return 0

        embeddings = self._embedder.embed_batch(chunks)

        for chunk_text, embedding in zip(chunks, embeddings, strict=True):
            await self._db.execute(
                text(
                    """
                    INSERT INTO code_embeddings
                        (repository_id, file_path, chunk_text, embedding)
                    VALUES
                        (:repository_id, :file_path, :chunk_text, :embedding)
                    """
                ),
                {
                    "repository_id": repository_id,
                    "file_path": file_path,
                    "chunk_text": chunk_text,
                    "embedding": str(embedding),
                },
            )

        logger.info(
            "File indexed",
            repository_id=repository_id,
            file_path=file_path,
            chunks=len(chunks),
        )
        return len(chunks)

    async def retrieve_context(self, repository_id: str, query: str, top_k: int = 8) -> str:
        """Return the top-k relevant code chunks for the given query as a formatted string."""
        query_embedding = self._embedder.embed(query)

        result = await self._db.execute(
            text(
                """
                SELECT file_path, chunk_text,
                       1 - (embedding <=> :query_embedding::vector) AS similarity
                FROM code_embeddings
                WHERE repository_id = :repository_id
                ORDER BY embedding <=> :query_embedding::vector
                LIMIT :top_k
                """
            ),
            {
                "repository_id": repository_id,
                "query_embedding": str(query_embedding),
                "top_k": top_k,
            },
        )
        rows = result.fetchall()

        if not rows:
            return ""

        parts = []
        for row in rows:
            parts.append(f"# {row.file_path} (similarity: {row.similarity:.3f})\n{row.chunk_text}")

        return "\n\n---\n\n".join(parts)

    async def delete_repository_embeddings(self, repository_id: str) -> None:
        await self._db.execute(
            text("DELETE FROM code_embeddings WHERE repository_id = :rid"),
            {"rid": repository_id},
        )
        logger.info("Repository embeddings deleted", repository_id=repository_id)
