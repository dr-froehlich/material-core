"""Template copy + placeholder substitution helpers.

Private module — shared by `matctl course add` and (via REQ-005)
`matctl doc add`. Templates live under `material_core/templates/<subdir>/`
and carry declared `{{TOKEN}}` placeholders that callers substitute after
the copy.
"""

from __future__ import annotations

import shutil
from importlib.resources import as_file, files
from pathlib import Path

import click

PLACEHOLDERS = ("{{COURSE_NAME}}", "{{COURSE_TITLE}}", "{{COURSE_SUBTITLE}}")


def copy_template(template_subdir: str, dest: Path) -> None:
    src_ref = files("material_core") / "templates" / template_subdir
    with as_file(src_ref) as src:
        if not src.is_dir():
            raise click.ClickException(f"template not found: {src}")
        try:
            shutil.copytree(src, dest, dirs_exist_ok=False)
        except FileExistsError as e:
            raise click.ClickException(f"{dest} already exists") from e


def substitute_placeholders(root: Path, values: dict[str, str]) -> None:
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new = content
        for token, value in values.items():
            new = new.replace(token, value)
        if new != content:
            p.write_text(new, encoding="utf-8")


def title_case_from_slug(name: str) -> str:
    return name.replace("-", " ").replace("_", " ").title()
