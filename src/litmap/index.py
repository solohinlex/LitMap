from __future__ import annotations

import math
import sqlite3
import struct
from collections.abc import Callable, Iterable
from pathlib import Path

from litmap.config import Project, Settings
from litmap.ingest import Chunk, Document, documents_to_chunks, load_corpus
from litmap.llm import embed_texts
from litmap.paths import project_index_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    path TEXT PRIMARY KEY,
    doc_type TEXT NOT NULL,
    title TEXT NOT NULL,
    mtime REAL NOT NULL,
    text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    heading TEXT NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB NOT NULL,
    FOREIGN KEY(path) REFERENCES documents(path) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS entities (
    name TEXT NOT NULL,
    alias TEXT NOT NULL,
    path TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    PRIMARY KEY (name, alias)
);

CREATE INDEX IF NOT EXISTS chunks_path_idx ON chunks(path);
"""


def packing_format(values: Iterable[float]) -> str:
    data = list(values)
    return f"{len(data)}f"


def dump_vector(values: list[float]) -> bytes:
    return struct.pack(packing_format(values), *values)


def load_vector(blob: bytes) -> list[float]:
    count = len(blob) // 4
    return list(struct.unpack(f"{count}f", blob))


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    norm_l = 0.0
    norm_r = 0.0
    for a, b in zip(left, right, strict=True):
        dot += a * b
        norm_l += a * a
        norm_r += b * b
    if norm_l <= 0 or norm_r <= 0:
        return 0.0
    return dot / math.sqrt(norm_l * norm_r)


def connect(project: Project) -> sqlite3.Connection:
    path = project_index_path(project.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def _upsert_document(conn: sqlite3.Connection, doc: Document) -> None:
    conn.execute(
        """
        INSERT INTO documents(path, doc_type, title, mtime, text)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            doc_type=excluded.doc_type,
            title=excluded.title,
            mtime=excluded.mtime,
            text=excluded.text
        """,
        (str(doc.path), doc.doc_type, doc.title, doc.mtime, doc.text),
    )


def _replace_chunks(conn: sqlite3.Connection, path: Path, chunks: list[Chunk], vectors: list[list[float]]) -> None:
    conn.execute("DELETE FROM chunks WHERE path = ?", (str(path),))
    for chunk, vector in zip(chunks, vectors, strict=True):
        conn.execute(
            """
            INSERT INTO chunks(path, chunk_index, heading, text, embedding)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(chunk.path), chunk.chunk_index, chunk.heading, chunk.text, dump_vector(vector)),
        )


def _rebuild_entities(conn: sqlite3.Connection, documents: list[Document]) -> None:
    conn.execute("DELETE FROM entities")
    for doc in documents:
        if doc.doc_type not in {"character", "plotline", "chapter"}:
            continue
        for alias in doc.aliases:
            conn.execute(
                """
                INSERT OR REPLACE INTO entities(name, alias, path, doc_type)
                VALUES (?, ?, ?, ?)
                """,
                (doc.title, alias, str(doc.path), doc.doc_type),
            )


def index_project(
    project: Project,
    settings: Settings,
    progress: Callable[[str], None] | None = None,
) -> dict[str, int]:
    documents = load_corpus(project.corpus)
    conn = connect(project)
    try:
        existing = {
            row["path"]: row["mtime"]
            for row in conn.execute("SELECT path, mtime FROM documents")
        }
        live_paths = {str(doc.path) for doc in documents}
        stale = [path for path in existing if path not in live_paths]
        for path in stale:
            conn.execute("DELETE FROM chunks WHERE path = ?", (path,))
            conn.execute("DELETE FROM documents WHERE path = ?", (path,))

        changed: list[Document] = []
        for doc in documents:
            previous = existing.get(str(doc.path))
            if previous is None or abs(previous - doc.mtime) > 1e-6:
                changed.append(doc)

        if progress:
            progress(f"файлов: {len(documents)}, к обновлению: {len(changed)}")

        for doc in changed:
            chunks = documents_to_chunks([doc])
            if not chunks:
                _upsert_document(conn, doc)
                conn.execute("DELETE FROM chunks WHERE path = ?", (str(doc.path),))
                continue
            if progress:
                progress(f"эмбеддинги: {doc.path}")
            vectors = embed_texts(settings, [chunk.text for chunk in chunks])
            _upsert_document(conn, doc)
            _replace_chunks(conn, doc.path, chunks, vectors)

        _rebuild_entities(conn, documents)
        conn.commit()
        chunk_count = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        return {
            "documents": len(documents),
            "updated": len(changed),
            "removed": len(stale),
            "chunks": int(chunk_count),
        }
    finally:
        conn.close()
