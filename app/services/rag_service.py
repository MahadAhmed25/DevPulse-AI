import base64
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.code_chunk import CodeChunk
from app.models.repository import Repository
from app.services import github_service
from app.services.embedding_service import EmbeddingService

logger = structlog.get_logger(__name__)

SKIP_DIRS = {".git", "node_modules", "__pycache__", "dist", "build", ".next", "vendor"}
SKIP_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".ico",
    ".svg",
    ".gif",
    ".woff",
    ".woff2",
    ".ttf",
    ".pdf",
    ".zip",
    ".lock",
    ".map",
    ".min.js",
}
MAX_FILE_BYTES = 100_000


class RAGService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._embedder = EmbeddingService()
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=100,
            separators=["\nclass ", "\ndef ", "\n\n", "\n", " ", ""],
        )

    async def _collect_files(
        self, access_token: str, full_name: str, path: str = ""
    ) -> list[dict[str, Any]]:
        """Recursively collect all file items from a GitHub repo path."""
        items = await github_service.get_repo_contents(access_token, full_name, path)
        # get_repo_contents may return a single dict for a file path — normalise
        if isinstance(items, dict):
            items = [items]

        files: list[dict[str, Any]] = []
        for item in items:
            item_path: str = item.get("path", "")
            # Skip if any path segment is in SKIP_DIRS
            if any(part in SKIP_DIRS for part in item_path.split("/")):
                continue
            if item.get("type") == "dir":
                files.extend(await self._collect_files(access_token, full_name, item_path))
            elif item.get("type") == "file":
                files.append(item)
        return files

    async def index_repository(self, repo_id: UUID, full_name: str, access_token: str) -> None:
        """Fetch, chunk, embed, and store all code from a GitHub repository."""
        # a. Collect all file paths recursively
        all_file_items = await self._collect_files(access_token, full_name)
        logger.info("Files collected", repo=full_name, count=len(all_file_items))

        # b & c. Fetch content and chunk files
        all_chunks: list[tuple[str, int, str]] = []  # (file_path, chunk_index, chunk_text)

        for file_item in all_file_items:
            file_path: str = file_item.get("path", "")

            # Skip by extension
            suffix = "." + file_path.rsplit(".", 1)[-1] if "." in file_path else ""
            if suffix in SKIP_EXTENSIONS:
                continue

            # Fetch file content (returns single dict with base64 content)
            try:
                result = await github_service.get_repo_contents(access_token, full_name, file_path)
                item = result if isinstance(result, dict) else result[0]
            except Exception as exc:
                logger.warning("Skipping file (fetch error)", path=file_path, error=str(exc))
                continue

            # Skip large files
            if item.get("size", 0) > MAX_FILE_BYTES:
                continue

            raw_content = item.get("content", "")
            if not raw_content:
                continue

            try:
                content = base64.b64decode(raw_content.replace("\n", "")).decode(
                    "utf-8", errors="ignore"
                )
            except Exception as exc:
                logger.warning("Skipping file (decode error)", path=file_path, error=str(exc))
                continue

            # c. Chunk the file
            chunks = self._splitter.split_text(content)
            for chunk_index, chunk_text in enumerate(chunks):
                all_chunks.append((file_path, chunk_index, chunk_text))

        logger.info(
            "Chunking complete",
            repo=full_name,
            total_chunks=len(all_chunks),
        )

        # d. Embed all chunks
        embeddings = await self._embedder.embed_texts([t for _, _, t in all_chunks])

        # e. Delete existing chunks for this repo
        await self._db.execute(delete(CodeChunk).where(CodeChunk.repository_id == repo_id))

        # f. Bulk insert new CodeChunk rows
        chunk_objects = [
            CodeChunk(
                repository_id=repo_id,
                file_path=file_path,
                chunk_index=chunk_index,
                content=chunk_text,
                embedding=embedding,
            )
            for (file_path, chunk_index, chunk_text), embedding in zip(all_chunks, embeddings)
        ]
        self._db.add_all(chunk_objects)
        await self._db.flush()

        # g. Update repository record — caller must have loaded the repo in this session
        repo_result = await self._db.execute(select(Repository).where(Repository.id == repo_id))
        repo = repo_result.scalar_one_or_none()
        if repo is not None:
            repo.is_indexed = True
            repo.index_status = "complete"
            repo.last_indexed_at = datetime.now(UTC)
            repo.index_error = None
            await self._db.flush()

        logger.info(
            "Repository indexed",
            repo=full_name,
            total_chunks=len(chunk_objects),
        )

    async def retrieve_context(self, repo_id: UUID, query: str, k: int = 8) -> list[str]:
        """Return the top-k relevant code chunks for the given query."""
        query_vec = await self._embedder.embed_text(query)

        rows = await self._db.execute(
            text(
                """
                SELECT content FROM code_chunks
                WHERE repository_id = :repo_id
                ORDER BY embedding <=> cast(:vec AS vector)
                LIMIT :k
                """
            ),
            {"repo_id": repo_id, "vec": query_vec, "k": k},
        )
        return [row.content for row in rows]
