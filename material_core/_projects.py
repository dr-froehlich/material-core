"""Round-trip helpers for the `projects.yml` manifest.

Private module — shared by `matctl project add/remove/modify` and
`matctl group add/remove/modify`. Uses `ruamel.yaml` so hand-edited
comments and formatting in the manifest survive a programmatic rewrite.

Brand defaults — two distinct defaults are deliberate:
  - Scaffold default = "generic". Written into new entries by add_project().
  - Resolution default = "thd". resolve_brand() returns "thd" when an entry
    has no brand: key, preserving backwards-compat for pre-REQ-014 manifests.
The two never conflict: by the time resolve_brand() runs on a fresh entry,
brand: is already populated.

Legacy normalisation — load_manifest calls _normalise_legacy to rewrite
type: course / type: doc entries into the new three-axis schema on every
load. The rewrite is persisted the next time save_manifest runs.
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


def _normalise_legacy(doc: CommentedMap) -> bool:
    """Rewrite legacy type:course/doc entries to the new three-axis schema in place.

    Returns True if any entry was rewritten.
    """
    changed = False
    for entry in doc.get("projects", []):
        t = entry.get("type")
        if t == "course":
            entry["type"] = "project"
            entry.setdefault("structure", "chapters")
            entry.setdefault("slides", True)
            entry.setdefault("brand", "thd")
            entry.setdefault("lang", "de")
            changed = True
        elif t == "doc":
            entry["type"] = "project"
            entry.setdefault("structure", "single")
            entry.setdefault("slides", False)
            entry.setdefault("brand", "thd")
            entry.setdefault("lang", "de")
            changed = True
    return changed


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
    _normalise_legacy(doc)
    return doc


def save_manifest(path: Path, doc: CommentedMap) -> None:
    with path.open("w", encoding="utf-8") as f:
        _yaml().dump(doc, f)


def project_names(doc: CommentedMap) -> list[str]:
    return [p["name"] for p in doc["projects"]]


def find_entry(doc: CommentedMap, name: str) -> CommentedMap | None:
    for p in doc["projects"]:
        if p["name"] == name:
            return p
    return None


def group_exists(doc: CommentedMap, name: str) -> bool:
    entry = find_entry(doc, name)
    return entry is not None and entry.get("type") == "group"


def dependents_of_group(doc: CommentedMap, group_name: str) -> list[str]:
    return [
        p["name"]
        for p in doc["projects"]
        if p.get("type") == "project"
        and p.get("group") == group_name
    ]


def add_project(
    doc: CommentedMap,
    name: str,
    title: str,
    structure: str,
    slides: bool,
    brand: str,
    lang: str,
    group: str | None = None,
) -> None:
    if name in project_names(doc):
        raise ValueError(f"{name} already in manifest")
    entry = CommentedMap()
    entry["name"] = name
    entry["type"] = "project"
    entry["title"] = title
    if group is not None:
        entry["group"] = group
    entry["structure"] = structure
    entry["slides"] = slides
    entry["brand"] = brand
    entry["lang"] = lang
    doc["projects"].append(entry)


def available_brands(pkg_root: Path) -> list[str]:
    """Sorted list of brand names found under pkg_root/brands/."""
    brands_dir = pkg_root / "brands"
    if not brands_dir.is_dir():
        return []
    return sorted(p.name for p in brands_dir.iterdir() if p.is_dir())


def resolve_brand(entry: CommentedMap) -> str:
    """Return the brand for an entry; falls back to 'thd' for legacy entries without brand:."""
    return entry.get("brand", "thd")


def add_group(doc: CommentedMap, name: str, title: str) -> None:
    if name in project_names(doc):
        raise ValueError(f"{name} already in manifest")
    entry = CommentedMap()
    entry["name"] = name
    entry["type"] = "group"
    entry["title"] = title
    doc["projects"].append(entry)


def remove_project(doc: CommentedMap, name: str) -> bool:
    projects = doc["projects"]
    for i, p in enumerate(projects):
        if p["name"] == name:
            del projects[i]
            return True
    return False


def remove_group(doc: CommentedMap, name: str) -> bool:
    dependents = dependents_of_group(doc, name)
    if dependents:
        raise ValueError(
            f"group {name} has dependents: {', '.join(dependents)}"
        )
    projects = doc["projects"]
    for i, p in enumerate(projects):
        if p["name"] == name and p.get("type") == "group":
            del projects[i]
            return True
    return False


def update_axes(
    entry: CommentedMap,
    *,
    brand: str | None = None,
    lang: str | None = None,
) -> list[str]:
    """Apply axis updates to an entry. Returns human-readable change list."""
    changes: list[str] = []
    if brand is not None:
        entry["brand"] = brand
        changes.append(f"brand → {brand!r}")
    if lang is not None:
        entry["lang"] = lang
        changes.append(f"lang → {lang!r}")
    return changes
