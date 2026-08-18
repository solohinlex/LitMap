from __future__ import annotations

from pathlib import Path

import yaml

from litmap.config import Settings
from litmap.llm import chat_complete
from litmap.paths import bundled_prompts_dir, project_prompts_dir
from litmap.retrieve import RetrievedChunk, format_context


def resolve_prompt_path(name: str, project_name: str | None = None) -> Path:
    filename = f"{name}.yaml"
    if project_name:
        override = project_prompts_dir(project_name) / filename
        if override.is_file():
            return override
    bundled = bundled_prompts_dir() / filename
    if not bundled.is_file():
        raise FileNotFoundError(f"Нет шаблона промпта: {name}")
    return bundled


def load_prompt(name: str, project_name: str | None = None) -> dict:
    path = resolve_prompt_path(name, project_name)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "system" not in data or "user" not in data:
        raise ValueError(f"В {path} нужны ключи system и user")
    return data


def render(template: str, **values: str) -> str:
    result = template
    for key, value in values.items():
        result = result.replace("{{" + key + "}}", value)
    return result


def synthesize(
    settings: Settings,
    prompt_name: str,
    question: str,
    chunks: list[RetrievedChunk],
    project_name: str | None = None,
    extra: dict[str, str] | None = None,
) -> str:
    prompt = load_prompt(prompt_name, project_name)
    context = format_context(chunks)
    if not context.strip():
        return "В этом проекте не найдено фрагментов по запросу."
    values = {"question": question, "context": context, **(extra or {})}
    system = render(prompt["system"], **values)
    user = render(prompt["user"], **values)
    return chat_complete(settings, system, user)
