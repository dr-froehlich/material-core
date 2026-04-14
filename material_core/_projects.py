"""Round-trip helpers for the `projects.yml` manifest.

Private module — shared by `matctl course add/remove` and (via REQ-005)
`matctl doc add/remove`. Uses `ruamel.yaml` so hand-edited comments and
formatting in the manifest survive a programmatic rewrite.
"""

from __future__ import annotations

from pathlib import Path

import click
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

PROJECTS_FILE = "projects.yml"


def _yaml() -> YAML:
    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def load_manifest(path: Path) -> CommentedMap:
    if not path.exists():
        raise click.ClickException(
            f"not in a material checkout: {PROJECTS_FILE} not found at {path}"
        )
    with path.open("r", encoding="utf-8") as f:
        doc = _yaml().load(f)
    if doc is None or "projects" not in doc:
        raise click.ClickException(
            f"{path} is missing the top-level `projects:` list"
        )
    return doc


def save_manifest(path: Path, doc: CommentedMap) -> None:
    with path.open("w", encoding="utf-8") as f:
        _yaml().dump(doc, f)


def project_names(doc: CommentedMap) -> list[str]:
    return [p["name"] for p in doc["projects"]]


def add_project(
    doc: CommentedMap, name: str, type_: str, group: str | None = None
) -> None:
    if name in project_names(doc):
        raise ValueError(f"{name} already in manifest")
    entry = CommentedMap()
    entry["name"] = name
    entry["type"] = type_
    if group is not None:
        entry["group"] = group
    doc["projects"].append(entry)


def remove_project(doc: CommentedMap, name: str) -> bool:
    projects = doc["projects"]
    for i, p in enumerate(projects):
        if p["name"] == name:
            del projects[i]
            return True
    return False
