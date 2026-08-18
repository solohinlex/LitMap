from __future__ import annotations

from pathlib import Path

from litmap.config import add_project, load_registry, project_from_cwd, resolve_project_name
from litmap.ingest import chunk_text, infer_type, parse_document, parse_frontmatter
from litmap.index import cosine


def test_parse_frontmatter_and_aliases(tmp_path: Path) -> None:
    path = tmp_path / "ivan.md"
    path.write_text(
        "---\ntype: character\nname: Иван\naliases:\n  - Ваня\n---\nГерой из степи.\n",
        encoding="utf-8",
    )
    doc = parse_document(path)
    assert doc.doc_type == "character"
    assert doc.title == "Иван"
    assert "Ваня" in doc.aliases
    assert "Иван" in doc.aliases


def test_infer_type_from_path(tmp_path: Path) -> None:
    path = tmp_path / "chapters" / "01.md"
    path.parent.mkdir()
    path.write_text("текст", encoding="utf-8")
    assert infer_type(path) == "chapter"


def test_chunk_by_headings() -> None:
    text = "# Один\n\nабзац один\n\n## Два\n\nабзац два\n"
    chunks = chunk_text(text, max_chars=80)
    headings = [heading for heading, _ in chunks]
    assert "Один" in headings
    assert "Два" in headings


def test_parse_frontmatter_absent() -> None:
    meta, body = parse_frontmatter("просто текст")
    assert meta == {}
    assert body == "просто текст"


def test_cosine_identical() -> None:
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_project_registry_isolation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LITMAP_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("LITMAP_DATA_DIR", str(tmp_path / "data"))
    a = tmp_path / "novel-a"
    b = tmp_path / "novel-b"
    a.mkdir()
    b.mkdir()
    add_project("alpha", [a])
    add_project("beta", [b])
    names = set(load_registry().projects)
    assert names == {"alpha", "beta"}
    assert resolve_project_name("alpha") == "alpha"
    assert project_from_cwd(a) == "alpha"
    assert project_from_cwd(b) == "beta"
    assert project_from_cwd(tmp_path) is None
