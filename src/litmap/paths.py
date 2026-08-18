from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from platformdirs import user_config_dir, user_data_dir

APP_NAME = "litmap"


def load_env_files() -> None:
    """Load .env without overriding already-set process variables, except LITMAP_ENV_FILE."""
    explicit = os.environ.get("LITMAP_ENV_FILE")
    if explicit:
        load_dotenv(explicit, override=True)
        return

    config_env = config_dir() / ".env"
    if config_env.is_file():
        load_dotenv(config_env, override=False)

    for parent in Path(__file__).resolve().parents:
        repo_env = parent / ".env"
        if repo_env.is_file() and (parent / "pyproject.toml").is_file():
            load_dotenv(repo_env, override=False)
            break

    load_dotenv(override=False)


def config_dir() -> Path:
    override = os.environ.get("LITMAP_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path(user_config_dir(APP_NAME, appauthor=False))


def data_dir() -> Path:
    override = os.environ.get("LITMAP_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path(user_data_dir(APP_NAME, appauthor=False))


def project_data_dir(name: str) -> Path:
    return data_dir() / "projects" / name


def project_index_path(name: str) -> Path:
    return project_data_dir(name) / "index.sqlite"


def project_prompts_dir(name: str) -> Path:
    return config_dir() / "projects" / name / "prompts"


def bundled_prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"
