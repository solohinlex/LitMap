from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from litmap.config import Project, Settings
from litmap.index import connect, cosine, load_vector
from litmap.llm import embed_texts


@dataclass
class RetrievedChunk:
    path: Path
    heading: str
    text: str
    score: float
    title: str = ""
    doc_type: str = ""
    work: str = ""


def format_context(chunks: list[RetrievedChunk], budget: int = 24000) -> str:
    parts: list[str] = []
    used = 0
    for chunk in chunks:
        heading = f" — {chunk.heading}" if chunk.heading else ""
        work = f"текст: {chunk.work} | " if chunk.work else ""
        block = f"### {work}файл: {chunk.path}{heading}\n{chunk.text.strip()}\n"
        if used + len(block) > budget and parts:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)


def _doc_field(info: sqlite3.Row | None, name: str, default: str = "") -> str:
    if info is None:
        return default
    try:
        value = info[name]
    except (IndexError, KeyError):
        return default
    return default if value is None else str(value)


def _chunk_from_row(
    row: sqlite3.Row,
    docs: dict[str, sqlite3.Row],
    score: float,
) -> RetrievedChunk:
    info = docs.get(row["path"])
    return RetrievedChunk(
        path=Path(row["path"]),
        heading=row["heading"],
        text=row["text"],
        score=score,
        title=_doc_field(info, "title"),
        doc_type=_doc_field(info, "doc_type"),
        work=_doc_field(info, "work"),
    )


def _document_map(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {row["path"]: row for row in conn.execute("SELECT path, doc_type, title, work FROM documents")}


def search_vector(conn: sqlite3.Connection, query_vec: list[float], limit: int = 12) -> list[RetrievedChunk]:
    docs = _document_map(conn)
    scored: list[RetrievedChunk] = []
    for row in conn.execute("SELECT path, heading, text, embedding FROM chunks"):
        score = cosine(query_vec, load_vector(row["embedding"]))
        scored.append(_chunk_from_row(row, docs, score))
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:limit]


def search_text(conn: sqlite3.Connection, needles: list[str], limit: int = 40) -> list[RetrievedChunk]:
    cleaned = [item.casefold() for item in needles if item and item.strip()]
    if not cleaned:
        return []
    docs = _document_map(conn)
    found: list[RetrievedChunk] = []
    for row in conn.execute("SELECT path, heading, text FROM chunks"):
        info = docs.get(row["path"])
        haystack = f"{_doc_field(info, 'work')}\n{row['heading']}\n{row['text']}".casefold()
        hits = sum(1 for needle in cleaned if needle in haystack)
        if not hits:
            continue
        found.append(_chunk_from_row(row, docs, float(hits)))
    found.sort(key=lambda item: item.score, reverse=True)
    return found[:limit]


def entity_aliases(conn: sqlite3.Connection, name: str, doc_type: str | None = None) -> list[str]:
    query = "SELECT name, alias, path, doc_type FROM entities"
    params: list[str] = []
    if doc_type:
        query += " WHERE doc_type = ?"
        params.append(doc_type)
    rows = conn.execute(query, params).fetchall()
    needle = name.casefold()
    aliases: list[str] = []
    matched_names: set[str] = set()
    for row in rows:
        if needle in row["alias"].casefold() or needle in row["name"].casefold():
            matched_names.add(row["name"])
    for row in rows:
        if row["name"] in matched_names:
            aliases.append(row["alias"])
    return list(dict.fromkeys(aliases))


def retrieve_for_question(
    project: Project,
    settings: Settings,
    question: str,
    extra_names: list[str] | None = None,
) -> list[RetrievedChunk]:
    conn = connect(project)
    try:
        query_vec = embed_texts(settings, [question])[0]
        vector_hits = search_vector(conn, query_vec, limit=12)
        tokens = _query_tokens(question)
        names = list(extra_names or [])
        names.extend(_known_names_in_text(conn, question))
        text_hits = search_text(conn, names + tokens, limit=20)
        merged = _merge_chunks(vector_hits, text_hits, limit=16)
        works = _works_in_text(conn, question)
        if not works:
            return merged
        preferred = [item for item in merged if item.work in works]
        rest = [item for item in merged if item.work not in works]
        return (preferred + rest)[:16]
    finally:
        conn.close()


def retrieve_entity(
    project: Project,
    settings: Settings,
    name: str,
    doc_type: str,
) -> list[RetrievedChunk]:
    conn = connect(project)
    try:
        aliases = entity_aliases(conn, name, doc_type=doc_type)
        needles = aliases or [name]
        mentions = search_text(conn, needles, limit=50)
        needle = name.casefold()
        sheet_paths = {
            Path(row["path"])
            for row in conn.execute(
                "SELECT name, alias, path FROM entities WHERE doc_type = ?",
                (doc_type,),
            )
            if needle in row["name"].casefold() or needle in row["alias"].casefold()
        }
        sheets: list[RetrievedChunk] = []
        docs = _document_map(conn)
        if sheet_paths:
            for row in conn.execute("SELECT path, heading, text FROM chunks"):
                if Path(row["path"]) not in sheet_paths:
                    continue
                sheets.append(_chunk_from_row(row, docs, 100.0))
        query_vec = embed_texts(settings, [name])[0]
        vector_hits = [
            item
            for item in search_vector(conn, query_vec, limit=16)
            if any(alias.casefold() in item.text.casefold() or alias.casefold() in item.heading.casefold() for alias in needles)
            or not aliases
        ]
        return _merge_chunks(sheets, mentions, vector_hits, limit=24)
    finally:
        conn.close()


def retrieve_by_title(
    project: Project,
    title: str,
    doc_type: str,
    work: str | None = None,
) -> list[RetrievedChunk]:
    conn = connect(project)
    try:
        docs = _document_map(conn)
        needle = title.casefold()
        work_needle = (work or "").casefold()
        hits: list[RetrievedChunk] = []
        for row in conn.execute("SELECT path, heading, text FROM chunks"):
            info = docs.get(row["path"])
            if not info:
                continue
            row_type = _doc_field(info, "doc_type")
            row_work = _doc_field(info, "work")
            if row_type != doc_type and doc_type != "chapter":
                continue
            if work_needle and work_needle not in row_work.casefold() and work_needle not in Path(row["path"]).as_posix().casefold():
                continue
            blob = (
                f"{_doc_field(info, 'title')} {row_work} "
                f"{Path(row['path']).stem} {row['heading']} {row['path']}"
            ).casefold()
            if needle not in blob and needle not in row["text"][:200].casefold():
                if row_type != doc_type:
                    continue
                if needle not in Path(row["path"]).as_posix().casefold():
                    continue
            score = 10.0 if row_type == doc_type else 5.0
            if row_work and (row_work.casefold() in needle or needle in row_work.casefold()):
                score += 5.0
            hits.append(_chunk_from_row(row, docs, score))
        hits.sort(key=lambda item: (-item.score, item.path.as_posix(), item.heading))
        return hits[:40]
    finally:
        conn.close()


def _merge_chunks(*groups: list[RetrievedChunk], limit: int) -> list[RetrievedChunk]:
    seen: set[tuple[str, str, str]] = set()
    merged: list[RetrievedChunk] = []
    for group in groups:
        for item in group:
            key = (str(item.path), item.heading, item.text[:80])
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= limit:
                return merged
    return merged


def _query_tokens(question: str) -> list[str]:
    tokens = re.findall(r"[^\W\d_]{4,}", question, flags=re.UNICODE)
    stop = {"этого", "этом", "какой", "какая", "какие", "дай", "сводка", "персонажу", "главе"}
    return [token for token in tokens if token.casefold() not in stop]


def _works_in_text(conn: sqlite3.Connection, text: str) -> list[str]:
    haystack = text.casefold()
    found: list[str] = []
    for row in conn.execute("SELECT DISTINCT work FROM documents WHERE work != ''"):
        work = row["work"]
        if work.casefold() in haystack:
            found.append(work)
    return found


def _known_names_in_text(conn: sqlite3.Connection, text: str) -> list[str]:
    haystack = text.casefold()
    found: list[str] = []
    for row in conn.execute("SELECT alias FROM entities"):
        alias = row["alias"]
        if len(alias) >= 3 and alias.casefold() in haystack:
            found.append(alias)
    return list(dict.fromkeys(found))
