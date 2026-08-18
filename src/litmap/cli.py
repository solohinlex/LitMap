from __future__ import annotations

from pathlib import Path

import click

from litmap.config import (
    LitMapError,
    add_project,
    get_project,
    load_registry,
    load_settings,
    remove_project,
    resolve_project_name,
)
from litmap.index import index_project
from litmap.router import answer_chapter, answer_character, answer_plotline, answer_question


def _fail(message: str) -> None:
    raise click.ClickException(message)


def _resolve(ctx: click.Context) -> str:
    try:
        return resolve_project_name(ctx.obj.get("project") if ctx.obj else None)
    except LitMapError as exc:
        _fail(str(exc))
        raise


@click.group()
@click.option("-p", "--project", envvar="LITMAP_PROJECT", default=None, help="Имя проекта из реестра.")
@click.pass_context
def cli(ctx: click.Context, project: str | None) -> None:
    ctx.ensure_object(dict)
    ctx.obj["project"] = project


@cli.group("projects")
def projects_group() -> None:
    """Реестр литературных проектов."""


@projects_group.command("add")
@click.argument("name")
@click.option(
    "--corpus",
    "corpus",
    multiple=True,
    required=True,
    type=click.Path(path_type=Path),
    help="Папка с текстами (можно повторять).",
)
def projects_add(name: str, corpus: tuple[Path, ...]) -> None:
    try:
        project = add_project(name, list(corpus))
    except LitMapError as exc:
        _fail(str(exc))
        return
    folders = "\n".join(f"  {path}" for path in project.corpus)
    click.echo(f"Проект {project.name} сохранён.\n{folders}")


@projects_group.command("list")
def projects_list() -> None:
    registry = load_registry()
    if not registry.projects:
        click.echo("Проектов нет. Добавьте: litmap projects add NAME --corpus DIR")
        return
    for name, project in sorted(registry.projects.items()):
        click.echo(name)
        for path in project.corpus:
            click.echo(f"  {path}")


@projects_group.command("remove")
@click.argument("name")
def projects_remove(name: str) -> None:
    try:
        remove_project(name)
    except LitMapError as exc:
        _fail(str(exc))
        return
    click.echo(f"Проект {name} удалён из реестра. Индекс на диске не тронут.")


@cli.command("index")
@click.pass_context
def index_cmd(ctx: click.Context) -> None:
    """Прочитать папки корпуса и обновить индекс проекта."""
    name = _resolve(ctx)
    try:
        settings = load_settings()
        project = get_project(name)
        stats = index_project(project, settings, progress=lambda msg: click.echo(msg, err=True))
    except LitMapError as exc:
        _fail(str(exc))
        return
    click.echo(
        f"{name}: документов {stats['documents']}, "
        f"обновлено {stats['updated']}, удалено {stats['removed']}, "
        f"чанков {stats['chunks']}"
    )


@cli.command("ask")
@click.argument("question")
@click.pass_context
def ask_cmd(ctx: click.Context, question: str) -> None:
    """Свободный вопрос по выбранному проекту."""
    name = _resolve(ctx)
    try:
        settings = load_settings()
        project = get_project(name)
        click.echo(answer_question(project, settings, question))
    except LitMapError as exc:
        _fail(str(exc))


@cli.command("character")
@click.argument("name")
@click.pass_context
def character_cmd(ctx: click.Context, name: str) -> None:
    """Сводка по персонажу."""
    project_name = _resolve(ctx)
    try:
        settings = load_settings()
        project = get_project(project_name)
        click.echo(answer_character(project, settings, name))
    except LitMapError as exc:
        _fail(str(exc))


@cli.command("chapter")
@click.argument("name")
@click.pass_context
def chapter_cmd(ctx: click.Context, name: str) -> None:
    """Сводка по главе."""
    project_name = _resolve(ctx)
    try:
        settings = load_settings()
        project = get_project(project_name)
        click.echo(answer_chapter(project, settings, name))
    except LitMapError as exc:
        _fail(str(exc))


@cli.command("plotline")
@click.argument("name")
@click.pass_context
def plotline_cmd(ctx: click.Context, name: str) -> None:
    """Сводка по сюжетной линии."""
    project_name = _resolve(ctx)
    try:
        settings = load_settings()
        project = get_project(project_name)
        click.echo(answer_plotline(project, settings, name))
    except LitMapError as exc:
        _fail(str(exc))


def main() -> None:
    cli(obj={})
