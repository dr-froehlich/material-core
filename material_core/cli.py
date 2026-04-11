"""matctl — command-line interface for material-core."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import click

LINK_TARGETS = ("_brand.yml", "shared")


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


@main.command()
def render() -> None:
    """Build courses (REQ-002)."""
    raise NotImplementedError("matctl render is planned for REQ-002")


@main.command()
def deploy() -> None:
    """Deploy built courses (REQ-002)."""
    raise NotImplementedError("matctl deploy is planned for REQ-002")


@main.command()
@click.argument("name")
def new(name: str) -> None:
    """Scaffold a new course or document (REQ-002)."""
    raise NotImplementedError("matctl new is planned for REQ-002")


if __name__ == "__main__":
    main()
