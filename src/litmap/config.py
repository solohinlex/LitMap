from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from litmap.paths import config_dir, load_env_files, project_prompts_dir

PROJECT_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


class LitMapError(Exception):
    """User-facing configuration or project error."""


@dataclass(frozen=True)
class Settings:
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    embed_base_url: str
    embed_model: str
    embed_api_key: str


@dataclass
class Project:
    name: str
    corpus: list[Path]


@dataclass
class Registry:
    projects: dict[str, Project] = field(default_factory=dict)


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise LitMapError(
            f"Не задана {name}. Скопируйте example.env в .env и заполните рабочие значения."
        )
    return value


def load_settings() -> Settings:
    load_env_files()
    return Settings(
        llm_base_url=_require_env("LITMAP_LLM_BASE_URL").rstrip("/"),
        llm_model=_require_env("LITMAP_LLM_MODEL"),
        llm_api_key=os.environ.get("LITMAP_LLM_API_KEY", "local").strip() or "local",
        embed_base_url=_require_env("LITMAP_EMBED_BASE_URL").rstrip("/"),
        embed_model=_require_env("LITMAP_EMBED_MODEL"),
        embed_api_key=os.environ.get("LITMAP_EMBED_API_KEY", "local").strip() or "local",
    )


def registry_path() -> Path:
    return config_dir() / "config.yaml"


def load_registry() -> Registry:
    path = registry_path()
    if not path.is_file():
        return Registry()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    projects_raw = raw.get("projects") or {}
    projects: dict[str, Project] = {}
    for name, spec in projects_raw.items():
        corpus = spec.get("corpus") if isinstance(spec, dict) else spec
        if not corpus:
            continue
        paths = [Path(item).expanduser().resolve() for item in corpus]
        projects[name] = Project(name=name, corpus=paths)
    return Registry(projects=projects)


def save_registry(registry: Registry) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "projects": {
            name: {"corpus": [str(p) for p in project.corpus]}
            for name, project in sorted(registry.projects.items())
        }
    }
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def validate_project_name(name: str) -> None:
    if not PROJECT_NAME_RE.match(name):
        raise LitMapError(
            "Имя проекта: латиница, цифры, дефис и подчёркивание; начинается с буквы или цифры."
        )


def add_project(name: str, corpus: list[Path]) -> Project:
    validate_project_name(name)
    resolved: list[Path] = []
    for item in corpus:
        path = item.expanduser().resolve()
        if not path.is_dir():
            raise LitMapError(f"Папка корпуса не найдена: {path}")
        resolved.append(path)
    if not resolved:
        raise LitMapError("Укажите хотя бы одну папку --corpus.")
    registry = load_registry()
    project = Project(name=name, corpus=resolved)
    registry.projects[name] = project
    save_registry(registry)
    project_prompts_dir(name).mkdir(parents=True, exist_ok=True)
    return project


def remove_project(name: str) -> None:
    registry = load_registry()
    if name not in registry.projects:
        raise LitMapError(f"Проект не найден: {name}")
    del registry.projects[name]
    save_registry(registry)


def get_project(name: str) -> Project:
    registry = load_registry()
    project = registry.projects.get(name)
    if project is None:
        raise LitMapError(f"Проект не найден: {name}. Смотрите: litmap projects list")
    return project


def project_from_cwd(cwd: Path | None = None) -> str | None:
    cwd = (cwd or Path.cwd()).resolve()
    matches: list[str] = []
    for name, project in load_registry().projects.items():
        for folder in project.corpus:
            if cwd == folder or folder in cwd.parents:
                matches.append(name)
                break
    unique = list(dict.fromkeys(matches))
    if len(unique) == 1:
        return unique[0]
    return None


def resolve_project_name(explicit: str | None, cwd: Path | None = None) -> str:
    if explicit:
        get_project(explicit)
        return explicit
    env_name = os.environ.get("LITMAP_PROJECT", "").strip()
    if env_name:
        get_project(env_name)
        return env_name
    inferred = project_from_cwd(cwd)
    if inferred:
        return inferred
    names = ", ".join(sorted(load_registry().projects)) or "(пусто)"
    raise LitMapError(
        "Укажите проект: litmap -p NAME ... или LITMAP_PROJECT.\n"
        f"Зарегистрированы: {names}"
    )
