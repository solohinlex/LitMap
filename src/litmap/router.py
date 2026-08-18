from __future__ import annotations

import re
from dataclasses import dataclass

from litmap.config import Project, Settings
from litmap.retrieve import (
    RetrievedChunk,
    retrieve_by_title,
    retrieve_entity,
    retrieve_for_question,
)
from litmap.synthesize import synthesize

CHARACTER_RE = re.compile(
    r"(?:сводк[ауие]|summary).{0,40}персонаж\w*\s+(.+)$",
    re.IGNORECASE,
)
CHAPTER_RE = re.compile(
    r"(?:сводк[ауие]|summary|что).{0,20}глав[еуыа]\s+(.+)$",
    re.IGNORECASE,
)
PLOT_RE = re.compile(
    r"(?:сводк[ауие]|summary).{0,40}(?:сюжетн\w*\s+лин\w*|lin(?:e|es))\s+(.+)$",
    re.IGNORECASE,
)


@dataclass
class Route:
    prompt: str
    chunks: list[RetrievedChunk]
    extra: dict[str, str]


def route_question(project: Project, settings: Settings, question: str) -> Route:
    text = question.strip()
    extra = {"subject": "", "work": ""}

    match = CHARACTER_RE.search(text)
    if match:
        name = match.group(1).strip(" ?«»\"'")
        extra["subject"] = name
        return Route(
            prompt="character_summary",
            chunks=retrieve_entity(project, settings, name, "character"),
            extra=extra,
        )

    match = CHAPTER_RE.search(text)
    if match:
        name = match.group(1).strip(" ?«»\"'")
        extra["subject"] = name
        extra["work"] = ""
        return Route(
            prompt="chapter_summary",
            chunks=retrieve_by_title(project, name, "chapter"),
            extra=extra,
        )

    match = PLOT_RE.search(text)
    if match:
        name = match.group(1).strip(" ?«»\"'")
        extra["subject"] = name
        return Route(
            prompt="plotline_summary",
            chunks=retrieve_entity(project, settings, name, "plotline"),
            extra=extra,
        )

    return Route(
        prompt="ask",
        chunks=retrieve_for_question(project, settings, text),
        extra=extra,
    )


def answer_question(project: Project, settings: Settings, question: str) -> str:
    routed = route_question(project, settings, question)
    return synthesize(
        settings,
        routed.prompt,
        question,
        routed.chunks,
        project_name=project.name,
        extra=routed.extra,
    )


def answer_character(project: Project, settings: Settings, name: str) -> str:
    chunks = retrieve_entity(project, settings, name, "character")
    question = f"Дай сводку по персонажу {name}"
    return synthesize(
        settings,
        "character_summary",
        question,
        chunks,
        project_name=project.name,
        extra={"subject": name},
    )


def answer_chapter(project: Project, settings: Settings, name: str, work: str | None = None) -> str:
    chunks = retrieve_by_title(project, name, "chapter", work=work)
    label = f"{work} / {name}" if work else name
    question = f"Дай сводку по главе {label}"
    return synthesize(
        settings,
        "chapter_summary",
        question,
        chunks,
        project_name=project.name,
        extra={"subject": name, "work": work or ""},
    )


def answer_plotline(project: Project, settings: Settings, name: str) -> str:
    chunks = retrieve_entity(project, settings, name, "plotline")
    question = f"Дай сводку по сюжетной линии {name}"
    return synthesize(
        settings,
        "plotline_summary",
        question,
        chunks,
        project_name=project.name,
        extra={"subject": name},
    )
