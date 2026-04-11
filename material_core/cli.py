"""matctl — command-line interface for material-core."""

from __future__ import annotations

import re
import shutil
from importlib.resources import files
from pathlib import Path

import click

from ._projects import (
    PROJECTS_FILE,
    add_project,
    load_manifest,
    project_names,
    remove_project,
    save_manifest,
)
from ._scaffold import (
    copy_template,
    substitute_placeholders,
    title_case_from_slug,
)

LINK_TARGETS = ("_brand.yml", "shared")

_NAME_RE = re.compile(r"[a-z0-9][a-z0-9._-]*")


def _package_root() -> Path:
    return Path(str(files("material_core")))


@click.group()
@click.version_option()
def main() -> None:
    """Tooling for the material content repository."""


@main.command()
@click.option(
    "--force",
    is_flag=True,
    help="Replace existing symlinks of the same name.",
)
def link(force: bool) -> None:
    """Symlink _brand.yml and shared/ from material-core into the current directory."""
    pkg = _package_root()
    cwd = Path.cwd()
    for name in LINK_TARGETS:
        src = pkg / name
        dst = cwd / name
        if not src.exists():
            raise click.ClickException(f"package data missing: {src}")
        if dst.is_symlink() or dst.exists():
            if not force:
                raise click.ClickException(
                    f"{dst} already exists; pass --force to replace"
                )
            if dst.is_symlink() or dst.is_file():
                dst.unlink()
            else:
                raise click.ClickException(
                    f"refusing to replace non-symlink directory: {dst}"
                )
        dst.symlink_to(src)
        click.echo(f"linked {name} -> {src}")


@main.command()
def unlink() -> None:
    """Remove the symlinks created by `matctl link`."""
    cwd = Path.cwd()
    for name in LINK_TARGETS:
        dst = cwd / name
        if dst.is_symlink():
            dst.unlink()
            click.echo(f"removed {name}")
        elif dst.exists():
            click.echo(f"skipped {name} (not a symlink)")


@main.group()
def course() -> None:
    """Manage courses in a material checkout."""


@course.command("add")
@click.argument("name")
@click.option(
    "--title",
    default=None,
    help="Human-readable title (default: <name> title-cased).",
)
@click.option(
    "--subtitle",
    default="",
    help="Optional subtitle (default: empty).",
)
def course_add(name: str, title: str | None, subtitle: str) -> None:
    """Scaffold a new course and register it in projects.yml."""
    if not _NAME_RE.fullmatch(name):
        raise click.ClickException(
            f"invalid course name {name!r}: must match [a-z0-9][a-z0-9._-]*"
        )
    cwd = Path.cwd()
    manifest_path = cwd / PROJECTS_FILE
    doc = load_manifest(manifest_path)
    if name in project_names(doc):
        raise click.ClickException(
            f"{name} already registered in {PROJECTS_FILE}"
        )
    dest = cwd / name
    if dest.exists():
        raise click.ClickException(f"{dest} already exists")

    resolved_title = title or title_case_from_slug(name)

    copy_template("course", dest)
    substitute_placeholders(
        dest,
        {
            "{{COURSE_NAME}}": name,
            "{{COURSE_TITLE}}": resolved_title,
            "{{COURSE_SUBTITLE}}": subtitle,
        },
    )
    add_project(doc, name, "course")
    save_manifest(manifest_path, doc)

    click.echo(f"created course {name} (title: {resolved_title!r})")
    click.echo("next steps:")
    click.echo(f"  quarto preview {name}")
    click.echo(f"  git add {name}/ {PROJECTS_FILE}")
    click.echo(f"  git commit -m 'Add course: {name}'")
    click.echo("  git push")


@course.command("remove")
@click.argument("name")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
def course_remove(name: str, yes: bool) -> None:
    """Remove a course from the manifest and delete its directory."""
    cwd = Path.cwd()
    manifest_path = cwd / PROJECTS_FILE
    doc = load_manifest(manifest_path)

    dest = cwd / name
    dir_exists = dest.exists()
    in_manifest = name in project_names(doc)

    if not dir_exists and not in_manifest:
        raise click.ClickException(
            f"nothing to remove: {name} is not in {PROJECTS_FILE} "
            f"and {dest} does not exist"
        )

    if dir_exists and not yes:
        if not click.confirm(
            f"delete directory {dest} (this is irreversible)?",
            default=False,
        ):
            raise click.ClickException("aborted")

    removed = []
    if in_manifest:
        remove_project(doc, name)
        save_manifest(manifest_path, doc)
        removed.append(f"{PROJECTS_FILE} entry")
    if dir_exists:
        shutil.rmtree(dest)
        removed.append(f"directory ./{name}/")

    click.echo(f"removed: {', '.join(removed)}")
    click.echo(
        "note: remote content at material.professorfroehlich.de/"
        f"{name}/ and any issued access tokens are NOT touched by this "
        "command — see docs/administration.md for manual cleanup."
    )


if __name__ == "__main__":
    main()
