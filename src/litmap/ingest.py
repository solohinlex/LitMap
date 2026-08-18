from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n?", re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*$", re.MULTILINE)
DEFAULT_MAX_CHARS = 1500
SPECIAL_FOLDERS = {
    "characters": "character",
    "character": "character",
    "lore": "lore",
    "chapters": "chapter",
    "chapter": "chapter",
    "plotlines": "plotline",
    "plotline": "plotline",
}


@dataclass
class Document:
    path: Path
    doc_type: str
    title: str
    text: str
    mtime: float
    work: str = ""
    aliases: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


@dataclass
class Chunk:
    path: Path
    chunk_index: int
    heading: str
    text: str
    doc_type: str
    title: str
    work: str = ""


def relative_to_corpus(path: Path, corpus_roots: list[Path] | None = None) -> Path:
    resolved = path.resolve()
    for root in corpus_roots or []:
        try:
            return resolved.relative_to(root.resolve())
        except ValueError:
            continue
    if len(resolved.parts) >= 2:
        return Path(*resolved.parts[-2:])
    return Path(resolved.name)


def infer_type_and_work(path: Path, corpus_roots: list[Path] | None = None) -> tuple[str, str]:
    """Special folders keep their type; any other top-level folder is a work of chapters."""
    relative = relative_to_corpus(path, corpus_roots)
    directories = list(relative.parts[:-1])
    doc_type = "chapter"
    for part in directories:
        mapped = SPECIAL_FOLDERS.get(part.lower())
        if mapped:
            doc_type = mapped
            break
    work = ""
    if directories:
        first = directories[0]
        if first.lower() not in SPECIAL_FOLDERS:
            work = first
    return doc_type, work


def infer_type(path: Path, corpus_roots: list[Path] | None = None) -> str:
    return infer_type_and_work(path, corpus_roots)[0]


def parse_frontmatter(raw: str) -> tuple[dict, str]:
    match = FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw
    meta = yaml.safe_load(match.group(1)) or {}
    if not isinstance(meta, dict):
        return {}, raw
    return meta, raw[match.end() :]


def _as_alias_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def parse_document(path: Path, corpus_roots: list[Path] | None = None) -> Document:
    raw = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(raw)
    inferred_type, inferred_work = infer_type_and_work(path, corpus_roots)
    doc_type = str(meta.get("type") or inferred_type)
    work = str(meta.get("work") or inferred_work)
    title = str(meta.get("name") or meta.get("title") or path.stem)
    aliases = _as_alias_list(meta.get("aliases"))
    if title not in aliases:
        aliases = [title, *aliases]
    stem = path.stem
    if stem not in aliases:
        aliases.append(stem)
    if work and work not in aliases:
        aliases.append(work)
    return Document(
        path=path.resolve(),
        doc_type=doc_type,
        title=title,
        text=body.strip() + "\n",
        mtime=path.stat().st_mtime,
        work=work,
        aliases=aliases,
        meta=meta,
    )


def _split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _pack_paragraphs(paragraphs: list[str], max_chars: int) -> list[str]:
    packed: list[str] = []
    buf: list[str] = []
    size = 0
    for para in paragraphs:
        extra = len(para) + (2 if buf else 0)
        if buf and size + extra > max_chars:
            packed.append("\n\n".join(buf))
            buf = [para]
            size = len(para)
        else:
            buf.append(para)
            size += extra
    if buf:
        packed.append("\n\n".join(buf))
    return packed or ([""] if not paragraphs else [])


def chunk_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[tuple[str, str]]:
    """Return (heading, chunk_text) pairs, preferring markdown headings."""
    if not text.strip():
        return []

    matches = list(HEADING_RE.finditer(text))
    sections: list[tuple[str, str]] = []
    if not matches:
        for packed in _pack_paragraphs(_split_paragraphs(text), max_chars):
            sections.append(("", packed))
        return sections

    preamble = text[: matches[0].start()].strip()
    if preamble:
        for packed in _pack_paragraphs(_split_paragraphs(preamble), max_chars):
            sections.append(("", packed))

    for i, match in enumerate(matches):
        heading = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        block = f"{match.group(0).strip()}\n\n{body}".strip() if body else match.group(0).strip()
        if len(block) <= max_chars:
            sections.append((heading, block))
            continue
        pieces = _pack_paragraphs(_split_paragraphs(body or heading), max_chars)
        for idx, piece in enumerate(pieces):
            prefix = f"{match.group(0).strip()}\n\n" if idx == 0 else ""
            sections.append((heading, (prefix + piece).strip()))
    return sections


def iter_text_files(corpus: list[Path]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for root in corpus:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if any(part.startswith(".") for part in path.relative_to(root).parts):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(resolved)
    return files


def load_corpus(corpus: list[Path]) -> list[Document]:
    return [parse_document(path, corpus) for path in iter_text_files(corpus)]


def documents_to_chunks(documents: list[Document], max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in documents:
        pieces = chunk_text(doc.text, max_chars=max_chars)
        for index, (heading, text) in enumerate(pieces):
            chunks.append(
                Chunk(
                    path=doc.path,
                    chunk_index=index,
                    heading=heading,
                    text=text,
                    doc_type=doc.doc_type,
                    title=doc.title,
                    work=doc.work,
                )
            )
    return chunks
