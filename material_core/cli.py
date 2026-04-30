"""matctl — command-line interface for material-core."""

from __future__ import annotations

import io
import json
import re
import secrets
import shutil
from datetime import date, timedelta
from importlib.resources import files
from pathlib import Path

import click
from ruamel.yaml import YAML

from ._brand_resolve import (
    brand_quarto_book_keys,
    link_project,
    relink_project,
    unlink_project,
)
from ._cloudflare import KVClient, load_credentials
from ._compose import compose
from ._landing import regenerate_group
from ._projects import (
    PROJECTS_FILE,
    add_group,
    add_project,
    available_brands,
    dependents_of_group,
    find_entry,
    group_exists,
    load_manifest,
    project_names,
    remove_group,
    remove_project,
    resolve_brand,
    save_manifest,
    update_axes,
)
from ._scaffold import (
    substitute_placeholders,
    title_case_from_slug,
)

SITE_BASE = "https://material.professorfroehlich.de"

LINK_TARGETS = ("shared",)

_NAME_RE = re.compile(r"[a-z0-9][a-z0-9._-]*")

_UNSET: object = object()


def _package_root() -> Path:
    return Path(str(files("material_core")))


def _regenerate_affected_groups(manifest, *groups: str | None) -> None:
    """Regenerate each unique, non-None group's landing page."""
    seen: set[str] = set()
    for g in groups:
        if g and g not in seen:
            seen.add(g)
            regenerate_group(Path.cwd(), g, manifest)


def _validate_name(name: str, label: str = "project") -> None:
    if not _NAME_RE.fullmatch(name):
        raise click.ClickException(
            f"invalid {label} name {name!r}: must match [a-z0-9][a-z0-9._-]*"
        )


def _scaffold_new_project(
    name: str,
    title: str,
    structure: str,
    slides: bool,
    brand: str,
    lang: str,
    subtitle: str = "",
    group: str | None = None,
) -> None:
    """Validate, compose template, patch manifest, echo next steps."""
    _validate_name(name)
    if group is not None:
        _validate_name(group, "group")

    cwd = Path.cwd()
    manifest_path = cwd / PROJECTS_FILE
    manifest = load_manifest(manifest_path)

    if name in project_names(manifest):
        raise click.ClickException(f"{name} already registered in {PROJECTS_FILE}")
    if group is not None and not group_exists(manifest, group):
        raise click.ClickException(
            f"group {group!r} not found in {PROJECTS_FILE} — "
            f"create it first with `matctl group add {group} --title ...`"
        )

    dest = cwd / name
    if dest.exists():
        raise click.ClickException(f"{dest} already exists")

    pkg = _package_root()

    placeholders = {
        "{{PROJECT_NAME}}": name,
        "{{PROJECT_TITLE}}": title,
        "{{PROJECT_SUBTITLE}}": subtitle,
        "{{LANG}}": lang,
    }

    compose(
        dest,
        structure=structure,
        slides=slides,
        brand=brand,
        placeholders=placeholders,
        pkg_root=pkg,
    )

    add_project(
        manifest,
        name,
        title=title,
        structure=structure,
        slides=slides,
        brand=brand,
        lang=lang,
        group=group,
    )
    save_manifest(manifest_path, manifest)
    _regenerate_affected_groups(manifest, group)

    click.echo(f"created project {name}")
    click.echo("next steps:")
    click.echo(f"  quarto preview {name}")
    click.echo(f"  git add {name}/ {PROJECTS_FILE}")
    click.echo(f"  git commit -m 'Add project: {name}'")
    click.echo("  git push")


def _remove_project(name: str, yes: bool) -> None:
    """Remove a project's manifest entry and directory."""
    cwd = Path.cwd()
    manifest_path = cwd / PROJECTS_FILE
    manifest = load_manifest(manifest_path)

    dest = cwd / name
    dir_exists = dest.exists()
    in_manifest = name in project_names(manifest)

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

    group: str | None = None
    if in_manifest:
        for p in manifest["projects"]:
            if p["name"] == name:
                group = p.get("group")
                break

    removed = []
    if in_manifest:
        remove_project(manifest, name)
        save_manifest(manifest_path, manifest)
        _regenerate_affected_groups(manifest, group)
        removed.append(f"{PROJECTS_FILE} entry")
    if dir_exists:
        shutil.rmtree(dest)
        removed.append(f"directory ./{name}/")

    click.echo(f"removed: {', '.join(removed)}")
    if group:
        remote_path = f"{group}/{name}/"
    elif in_manifest:
        remote_path = f"{name}/"
    else:
        remote_path = f"{name}/ (remote path depends on the original group, if any)"
    click.echo(
        f"note: remote content at material.professorfroehlich.de/"
        f"{remote_path} and any issued access tokens are NOT touched by this "
        "command — see docs/administration.md for manual cleanup."
    )


def _rewrite_title(structure: str, dest: Path, new_title: str) -> None:
    """Write-through the new title into the scaffolded file."""
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    if structure == "chapters":
        target = dest / "_quarto.yml"
        if not target.exists():
            raise click.ClickException(
                f"cannot rewrite title: {target} does not exist"
            )
        with target.open("r", encoding="utf-8") as f:
            doc = yaml.load(f)
        if doc is None or "book" not in doc or "title" not in doc["book"]:
            raise click.ClickException(
                f"{target} has no `book.title` key — refusing to rewrite; "
                "fix the file by hand"
            )
        doc["book"]["title"] = new_title
        with target.open("w", encoding="utf-8") as f:
            yaml.dump(doc, f)
        return

    if structure == "single":
        target = dest / "index.qmd"
        if not target.exists():
            raise click.ClickException(
                f"cannot rewrite title: {target} does not exist"
            )
        text = target.read_text(encoding="utf-8")
        lines = text.split("\n")
        if not lines or lines[0].rstrip() != "---":
            raise click.ClickException(
                f"{target} has no leading `---` front-matter block — "
                "refusing to rewrite; fix the file by hand"
            )
        close_idx: int | None = None
        for i in range(1, len(lines)):
            if lines[i].rstrip() == "---":
                close_idx = i
                break
        if close_idx is None:
            raise click.ClickException(
                f"{target} has an unterminated front-matter block — "
                "refusing to rewrite; fix the file by hand"
            )
        front_src = "\n".join(lines[1:close_idx]) + "\n"
        front = yaml.load(front_src)
        if front is None:
            raise click.ClickException(
                f"{target} has an empty front-matter block — "
                "refusing to rewrite; fix the file by hand"
            )
        front["title"] = new_title
        buf = io.StringIO()
        yaml.dump(front, buf)
        new_front = buf.getvalue().rstrip("\n").split("\n")
        new_lines = ["---", *new_front, "---", *lines[close_idx + 1:]]
        target.write_text("\n".join(new_lines), encoding="utf-8")
        return

    raise click.ClickException(f"unknown structure for title rewrite: {structure}")


def _rewrite_lang(structure: str, dest: Path, new_lang: str) -> None:
    """Rewrite the lang key in _quarto.yml (chapters) or index.qmd front matter (single)."""
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    if structure == "chapters":
        target = dest / "_quarto.yml"
        if not target.exists():
            raise click.ClickException(f"cannot rewrite lang: {target} does not exist")
        with target.open("r", encoding="utf-8") as f:
            doc = yaml.load(f)
        if doc is None:
            raise click.ClickException(f"{target} is empty")
        doc["lang"] = new_lang
        with target.open("w", encoding="utf-8") as f:
            yaml.dump(doc, f)
        return

    if structure == "single":
        target = dest / "index.qmd"
        if not target.exists():
            raise click.ClickException(f"cannot rewrite lang: {target} does not exist")
        text = target.read_text(encoding="utf-8")
        lines = text.split("\n")
        if not lines or lines[0].rstrip() != "---":
            raise click.ClickException(
                f"{target} has no leading `---` front-matter block"
            )
        close_idx: int | None = None
        for i in range(1, len(lines)):
            if lines[i].rstrip() == "---":
                close_idx = i
                break
        if close_idx is None:
            raise click.ClickException(f"{target} has an unterminated front-matter block")
        front_src = "\n".join(lines[1:close_idx]) + "\n"
        front = yaml.load(front_src)
        if front is None:
            front = {}
        front["lang"] = new_lang
        buf = io.StringIO()
        yaml.dump(front, buf)
        new_front = buf.getvalue().rstrip("\n").split("\n")
        new_lines = ["---", *new_front, "---", *lines[close_idx + 1:]]
        target.write_text("\n".join(new_lines), encoding="utf-8")
        return

    raise click.ClickException(f"unknown structure for lang rewrite: {structure}")


def _rewrite_brand_in_quarto(dest: Path, brand: str) -> None:
    """Update or remove book.favicon and book.sidebar.logo in _quarto.yml."""
    target = dest / "_quarto.yml"
    if not target.exists():
        return  # single-file project — no book keys to update
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    with target.open("r", encoding="utf-8") as f:
        doc = yaml.load(f)
    if doc is None or "book" not in doc:
        return
    book_keys = brand_quarto_book_keys(brand)
    if book_keys:
        doc["book"]["favicon"] = book_keys["favicon"]
        if "sidebar" not in doc["book"]:
            from ruamel.yaml.comments import CommentedMap
            doc["book"]["sidebar"] = CommentedMap()
        doc["book"]["sidebar"]["logo"] = book_keys["logo"]
    else:
        # generic brand: remove favicon and sidebar.logo
        doc["book"].pop("favicon", None)
        if "sidebar" in doc["book"]:
            doc["book"]["sidebar"].pop("logo", None)
            if not doc["book"]["sidebar"]:
                doc["book"].pop("sidebar", None)
    with target.open("w", encoding="utf-8") as f:
        yaml.dump(doc, f)


@click.group()
@click.version_option()
def main() -> None:
    """Tooling for the material content repository."""


# ---------------------------------------------------------------------------
# project group
# ---------------------------------------------------------------------------

@main.group("project")
def project_cmd() -> None:
    """Manage projects (courses, documents) in a material checkout."""


@project_cmd.command("add")
@click.argument("name")
@click.option(
    "--structure",
    required=True,
    type=click.Choice(["chapters", "single"]),
    help="Document structure: multi-chapter book or single-file document.",
)
@click.option(
    "--slides/--no-slides",
    required=True,
    default=None,
    help="Include a slides/ subdirectory.",
)
@click.option(
    "--brand",
    required=True,
    type=click.Choice(available_brands(_package_root())),
    help="Visual brand (logo, colours, footer).",
)
@click.option(
    "--lang",
    required=True,
    type=click.Choice(["de", "en"]),
    help="Document language (sets crossref label language).",
)
@click.option(
    "--title",
    default=None,
    help="Human-readable title (default: <name> title-cased).",
)
@click.option(
    "--subtitle",
    default="",
    help="Optional subtitle (only used when --structure chapters).",
)
@click.option(
    "--group",
    default=None,
    help="Optional URL-path group; deploys under <group>/<name>/.",
)
def project_add(
    name: str,
    structure: str,
    slides: bool,
    brand: str,
    lang: str,
    title: str | None,
    subtitle: str,
    group: str | None,
) -> None:
    """Scaffold a new project and register it in projects.yml."""
    if subtitle and structure == "single":
        raise click.UsageError("--subtitle is only meaningful with --structure chapters")
    resolved_title = title or title_case_from_slug(name)
    _scaffold_new_project(
        name=name,
        title=resolved_title,
        structure=structure,
        slides=slides,
        brand=brand,
        lang=lang,
        subtitle=subtitle,
        group=group,
    )


@project_cmd.command("remove")
@click.argument("name")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
def project_remove(name: str, yes: bool) -> None:
    """Remove a project from the manifest and delete its directory."""
    _remove_project(name, yes)


@project_cmd.command("modify")
@click.argument("name")
@click.option(
    "--title",
    default=_UNSET,
    type=click.UNPROCESSED,
    help="New human-readable title (write-through to _quarto.yml or index.qmd).",
)
@click.option(
    "--group",
    default=_UNSET,
    type=click.UNPROCESSED,
    help="New group (must exist); pass empty string to remove grouping.",
)
@click.option(
    "--brand",
    default=_UNSET,
    type=click.UNPROCESSED,
    help="New visual brand; rewires per-project symlinks and updates _quarto.yml.",
)
@click.option(
    "--slides/--no-slides",
    default=None,
    help="Add slides/ overlay (false→true only; true→false rejected when slides/ has content).",
)
@click.option(
    "--lang",
    default=_UNSET,
    type=click.UNPROCESSED,
    help="New document language.",
)
@click.option(
    "--structure",
    default=_UNSET,
    type=click.UNPROCESSED,
    help="Structure axis — always rejected; create a new project and move content by hand.",
)
def project_modify(
    name: str,
    title: object,
    group: object,
    brand: object,
    slides: bool | None,
    lang: object,
    structure: object,
) -> None:
    """Modify a project's metadata, brand, language, or slides presence."""
    if structure is not _UNSET:
        raise click.ClickException(
            "--structure flip not supported automatically; "
            "create a new project and move content by hand"
        )

    has_change = any(
        x is not _UNSET for x in (title, group, brand, lang)
    ) or slides is not None
    if not has_change:
        raise click.UsageError(
            "specify at least one of --title, --group, --brand, --slides/--no-slides, --lang"
        )

    cwd = Path.cwd()
    manifest_path = cwd / PROJECTS_FILE
    manifest = load_manifest(manifest_path)
    entry = find_entry(manifest, name)
    if entry is None:
        raise click.ClickException(f"{name} not found in {PROJECTS_FILE}")
    if entry.get("type") != "project":
        raise click.ClickException(
            f"{name} is type {entry.get('type')!r}, not 'project'"
        )

    proj_structure = entry.get("structure", "chapters")
    old_group = entry.get("group")
    changes: list[str] = []
    group_changed = False
    dest = cwd / name

    # --title
    if title is not _UNSET:
        if not isinstance(title, str) or title == "":
            raise click.ClickException("--title must not be empty")
        entry["title"] = title
        _rewrite_title(proj_structure, dest, title)
        changes.append(f"title → {title!r}")

    # --group
    if group is not _UNSET:
        assert isinstance(group, str)
        if group == "":
            if "group" in entry:
                del entry["group"]
            changes.append("group removed")
            group_changed = True
        else:
            if not _NAME_RE.fullmatch(group):
                raise click.ClickException(
                    f"invalid group name {group!r}: must match [a-z0-9][a-z0-9._-]*"
                )
            if not group_exists(manifest, group):
                raise click.ClickException(
                    f"group {group!r} not found in {PROJECTS_FILE} — "
                    f"create it first with `matctl group add {group} --title ...`"
                )
            entry["group"] = group
            changes.append(f"group → {group!r}")
            group_changed = True

    # --brand
    if brand is not _UNSET:
        assert isinstance(brand, str)
        pkg = _package_root()
        valid = available_brands(pkg)
        if brand not in valid:
            raise click.ClickException(
                f"unknown brand {brand!r}: choose one of {', '.join(valid)}"
            )
        update_axes(entry, brand=brand)
        relink_project(dest, brand, pkg)
        _rewrite_brand_in_quarto(dest, brand)
        changes.append(f"brand → {brand!r}")

    # --slides
    if slides is not None:
        current_slides = entry.get("slides", False)
        if slides and not current_slides:
            # false → true: add slides overlay
            slides_dest = dest / "slides"
            slides_dest.mkdir(exist_ok=True)
            from importlib.resources import as_file
            with as_file(files("material_core") / "templates" / "slides") as slides_src:
                from ._compose import _overlay_copy
                _overlay_copy(slides_src, slides_dest)
            proj_title = str(entry.get("title", name))
            proj_lang = str(entry.get("lang", "de"))
            proj_brand = str(entry.get("brand", "generic"))
            from ._brand_resolve import brand_placeholders
            substitute_placeholders(slides_dest, {
                "{{PROJECT_NAME}}": name,
                "{{PROJECT_TITLE}}": proj_title,
                "{{PROJECT_SUBTITLE}}": "",
                "{{LANG}}": proj_lang,
                **brand_placeholders(proj_brand),
            })
            entry["slides"] = True
            changes.append("slides → true (overlay added)")
        elif not slides and current_slides:
            slides_dir = dest / "slides"
            if slides_dir.exists():
                raise click.ClickException(
                    "cannot set --no-slides: slides/ directory exists with content — "
                    "remove it by hand and then run: matctl project modify "
                    f"{name} --no-slides"
                )
            entry["slides"] = False
            changes.append("slides → false")
        else:
            click.echo(f"slides already {'true' if slides else 'false'} — no change")

    # --lang
    if lang is not _UNSET:
        assert isinstance(lang, str)
        if lang not in ("de", "en"):
            raise click.ClickException(f"--lang must be 'de' or 'en', got {lang!r}")
        update_axes(entry, lang=lang)
        _rewrite_lang(proj_structure, dest, lang)
        changes.append(f"lang → {lang!r}")

    save_manifest(manifest_path, manifest)

    if group_changed:
        _regenerate_affected_groups(manifest, old_group, entry.get("group"))
    else:
        _regenerate_affected_groups(manifest, old_group)

    click.echo(f"modified project {name}: {', '.join(changes)}")
    if group_changed:
        click.echo(
            "note: remote content at the old deploy path on "
            "material.professorfroehlich.de is NOT moved by this command — "
            "it will become stale on the next CI run and must be cleaned up "
            "manually. See docs/administration.md."
        )


# ---------------------------------------------------------------------------
# link / unlink
# ---------------------------------------------------------------------------

@main.command()
@click.option(
    "--force",
    is_flag=True,
    help="Replace existing symlinks of the same name.",
)
def link(force: bool) -> None:
    """Wire brand and shared/ symlinks for all projects (or just the current project dir)."""
    pkg = _package_root()
    cwd = Path.cwd()

    root_manifest = cwd / PROJECTS_FILE
    parent_manifest = cwd.parent / PROJECTS_FILE

    if root_manifest.exists():
        manifest = load_manifest(root_manifest)
        _ensure_shared_symlink(cwd, pkg, force)
        for entry in manifest["projects"]:
            if entry.get("type") != "project":
                continue
            name = entry["name"]
            brand = resolve_brand(entry)
            project_dir = cwd / name
            if not project_dir.is_dir():
                click.echo(f"skipping {name} (directory not found)")
                continue
            link_project(project_dir, brand, pkg, force=force)
            click.echo(f"linked {name} → brand:{brand}")
        click.echo("linked shared/")
    elif parent_manifest.exists():
        manifest = load_manifest(parent_manifest)
        name = cwd.name
        entry = find_entry(manifest, name)
        if entry is None or entry.get("type") != "project":
            raise click.ClickException(
                f"{name} is not a project in {parent_manifest}"
            )
        brand = resolve_brand(entry)
        link_project(cwd, brand, pkg, force=force)
        _ensure_shared_symlink(cwd.parent, pkg, force)
        click.echo(f"linked {name} → brand:{brand}")
        click.echo("linked shared/")
    else:
        raise click.ClickException(
            f"no {PROJECTS_FILE} found in {cwd} or {cwd.parent}"
        )


def _ensure_shared_symlink(repo_root: Path, pkg: Path, force: bool) -> None:
    src = pkg / "shared"
    dst = repo_root / "shared"
    if not src.exists():
        raise click.ClickException(f"package data missing: {src}")
    if dst.is_symlink() or dst.exists():
        if not force:
            return
        if dst.is_symlink() or dst.is_file():
            dst.unlink()
        else:
            raise click.ClickException(
                f"refusing to replace non-symlink directory: {dst}"
            )
    dst.symlink_to(src)


@main.command()
def unlink() -> None:
    """Remove brand and shared/ symlinks (root mode) or just this project's symlinks."""
    cwd = Path.cwd()
    root_manifest = cwd / PROJECTS_FILE
    parent_manifest = cwd.parent / PROJECTS_FILE

    if root_manifest.exists():
        manifest = load_manifest(root_manifest)
        for entry in manifest["projects"]:
            if entry.get("type") != "project":
                continue
            name = entry["name"]
            project_dir = cwd / name
            if project_dir.is_dir():
                unlink_project(project_dir)
                click.echo(f"unlinked {name}")
        _remove_symlink(cwd / "shared")
    elif parent_manifest.exists():
        name = cwd.name
        unlink_project(cwd)
        click.echo(f"unlinked {name}")
    else:
        raise click.ClickException(
            f"no {PROJECTS_FILE} found in {cwd} or {cwd.parent}"
        )


def _remove_symlink(dst: Path) -> None:
    if dst.is_symlink():
        dst.unlink()
        click.echo(f"removed {dst.name}")
    elif dst.exists():
        click.echo(f"skipped {dst.name} (not a symlink)")


# ---------------------------------------------------------------------------
# group group
# ---------------------------------------------------------------------------

@main.group("group")
def group_cmd() -> None:
    """Manage project groups in a material checkout."""


@group_cmd.command("add")
@click.argument("name")
@click.option("--title", required=True, help="Human-readable title.")
def group_add(name: str, title: str) -> None:
    """Register a new group in projects.yml."""
    if not _NAME_RE.fullmatch(name):
        raise click.ClickException(
            f"invalid group name {name!r}: must match [a-z0-9][a-z0-9._-]*"
        )
    if title == "":
        raise click.ClickException("--title must not be empty")

    cwd = Path.cwd()
    manifest_path = cwd / PROJECTS_FILE
    manifest = load_manifest(manifest_path)
    try:
        add_group(manifest, name, title)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from None
    save_manifest(manifest_path, manifest)
    regenerate_group(Path.cwd(), name, manifest)
    click.echo(f"created group {name}")


@group_cmd.command("remove")
@click.argument("name")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
def group_remove(name: str, yes: bool) -> None:
    """Remove a group from projects.yml (fails if any dependents remain)."""
    cwd = Path.cwd()
    manifest_path = cwd / PROJECTS_FILE
    manifest = load_manifest(manifest_path)

    entry = find_entry(manifest, name)
    if entry is None:
        raise click.ClickException(f"{name} not found in {PROJECTS_FILE}")
    if entry.get("type") != "group":
        raise click.ClickException(
            f"{name} is a {entry.get('type')!r}, not a 'group'"
        )

    dependents = dependents_of_group(manifest, name)
    if dependents:
        raise click.ClickException(
            f"group {name} has dependents — remove or re-group them first: "
            f"{', '.join(dependents)}"
        )

    if not yes:
        if not click.confirm(
            f"remove group {name} from {PROJECTS_FILE}?", default=False
        ):
            raise click.ClickException("aborted")

    remove_group(manifest, name)
    save_manifest(manifest_path, manifest)
    click.echo(f"removed group {name}")


@group_cmd.command("modify")
@click.argument("name")
@click.option(
    "--title",
    default=_UNSET,
    type=click.UNPROCESSED,
    help="New human-readable title for the group.",
)
def group_modify(name: str, title: object) -> None:
    """Modify a group's title."""
    if title is _UNSET:
        raise click.UsageError("specify --title")
    if not isinstance(title, str) or title == "":
        raise click.ClickException("--title must not be empty")

    cwd = Path.cwd()
    manifest_path = cwd / PROJECTS_FILE
    manifest = load_manifest(manifest_path)
    entry = find_entry(manifest, name)
    if entry is None:
        raise click.ClickException(f"{name} not found in {PROJECTS_FILE}")
    if entry.get("type") != "group":
        raise click.ClickException(
            f"{name} is a {entry.get('type')!r}, not a 'group'"
        )
    entry["title"] = title
    save_manifest(manifest_path, manifest)
    regenerate_group(Path.cwd(), name, manifest)
    click.echo(f"modified group {name}: title → {title!r}")


# ---------------------------------------------------------------------------
# token group
# ---------------------------------------------------------------------------

@main.group()
def token() -> None:
    """Manage lecture access tokens."""


@token.command("issue")
@click.argument("course")
@click.argument("label")
@click.option(
    "--days",
    type=int,
    default=365,
    show_default=True,
    help="Validity period in days.",
)
def token_issue(course: str, label: str, days: int) -> None:
    """Issue a new access token for COURSE with LABEL."""
    account_id, api_token, namespace_id = load_credentials()
    tok = secrets.token_hex(12)
    issued = date.today().isoformat()
    expires = (date.today() + timedelta(days=days)).isoformat()

    with KVClient(account_id, api_token, namespace_id) as kv:
        kv.put(
            f"tok:{tok}",
            {
                "course": course,
                "label": label,
                "issued": issued,
                "expires": expires,
            },
        )

    click.echo("")
    click.echo("Token issued successfully.")
    click.echo("")
    click.echo(f"  Token  : {tok}")
    click.echo(f"  Course : {course}")
    click.echo(f"  Label  : {label}")
    click.echo(f"  Issued : {issued}")
    click.echo(f"  Expires: {expires} ({days} days)")
    click.echo("")
    if course == "*":
        click.echo(f"  iLearn link (all courses): {SITE_BASE}/?token={tok}")
    else:
        click.echo(f"  iLearn link: {SITE_BASE}/{course}/?token={tok}")
    click.echo("")


@token.command("list")
@click.argument("course", required=False)
def token_list(course: str | None) -> None:
    """List access tokens, optionally filtered to one COURSE."""
    account_id, api_token, namespace_id = load_credentials()

    with KVClient(account_id, api_token, namespace_id) as kv:
        keys = kv.list_keys("tok:")
        if not keys:
            click.echo("No tokens found.")
            return

        today = date.today()
        rows: list[tuple[str, str, str, str, str]] = []
        for key in keys:
            tok = key[len("tok:"):] if key.startswith("tok:") else key
            raw = kv.get(key) or {}
            row_course = str(raw.get("course", ""))
            if course is not None and row_course != course:
                continue
            label = str(raw.get("label", ""))
            issued = str(raw.get("issued", ""))
            expires = str(raw.get("expires", ""))
            if expires:
                try:
                    if date.fromisoformat(expires) < today:
                        expires = f"{expires} [EXPIRED]"
                except ValueError:
                    pass
            rows.append((tok, row_course, label, issued, expires))

    if not rows:
        click.echo("No tokens found.")
        return

    headers = ("TOKEN", "COURSE", "LABEL", "ISSUED", "EXPIRES")
    widths = [
        max(len(headers[i]), max(len(row[i]) for row in rows))
        for i in range(len(headers))
    ]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    click.echo(fmt.format(*headers))
    click.echo(fmt.format(*("-" * w for w in widths)))
    for row in rows:
        click.echo(fmt.format(*row))


@token.command("revoke")
@click.argument("token_value")
def token_revoke(token_value: str) -> None:
    """Revoke (delete) the KV entry for TOKEN_VALUE.

    Session cookies remain valid until COOKIE_SECRET rotation — see
    docs/administration.md §7.
    """
    account_id, api_token, namespace_id = load_credentials()
    with KVClient(account_id, api_token, namespace_id) as kv:
        deleted = kv.delete(f"tok:{token_value}")

    if deleted:
        click.echo(f"Token '{token_value}' revoked.")
    else:
        click.echo(f"Token '{token_value}' not found (already revoked?).")


@token.command("show")
@click.argument("token_value")
def token_show(token_value: str) -> None:
    """Print raw KV metadata for TOKEN_VALUE."""
    account_id, api_token, namespace_id = load_credentials()
    with KVClient(account_id, api_token, namespace_id) as kv:
        raw = kv.get(f"tok:{token_value}")
    if raw is None:
        raise click.ClickException("token not found")
    click.echo(json.dumps(raw, indent=2))


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

def _quarto_data_dir() -> Path:
    """Return the Quarto user data directory for the current platform."""
    import os
    import sys

    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "quarto"
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        return Path(appdata) / "quarto"
    xdg = os.environ.get("XDG_DATA_HOME", "")
    base = Path(xdg) if xdg else home / ".local" / "share"
    return base / "quarto"


@main.command()
@click.option(
    "--install",
    is_flag=True,
    help="Install missing dependencies automatically (runs quarto install …).",
)
def doctor(install: bool) -> None:
    """Check local prerequisites for PDF rendering with Mermaid diagrams.

    Exits 0 if all checks pass, 1 if any check fails.
    """
    import shutil
    import subprocess

    all_ok = True

    # --- quarto on PATH ---
    quarto_bin = shutil.which("quarto")
    if quarto_bin:
        click.echo("  [OK]   quarto: found")
    else:
        click.echo("  [FAIL] quarto: not found on PATH")
        click.echo("         Install Quarto from https://quarto.org/docs/get-started/")
        all_ok = False

    # --- chrome-headless-shell for Mermaid → PDF ---
    chrome_dir = _quarto_data_dir() / "chrome-headless-shell"
    chrome_installed = chrome_dir.exists() and any(chrome_dir.iterdir())

    if chrome_installed:
        click.echo("  [OK]   chrome-headless-shell: found (Mermaid → PDF)")
    elif install:
        if not quarto_bin:
            click.echo("  [FAIL] chrome-headless-shell: cannot install — quarto not on PATH")
            all_ok = False
        else:
            click.echo("  [--]   chrome-headless-shell: not found — installing...")
            result = subprocess.run(
                ["quarto", "install", "chrome-headless-shell", "--no-prompt"],
            )
            if result.returncode == 0:
                click.echo("  [OK]   chrome-headless-shell: installed")
            else:
                click.echo(
                    f"  [FAIL] chrome-headless-shell: install exited {result.returncode}"
                )
                all_ok = False
    else:
        click.echo("  [FAIL] chrome-headless-shell: not found")
        click.echo(
            "         {mermaid} blocks will be missing or silently skipped in"
        )
        click.echo("         orange-book-typst (PDF) output without this tool.")
        click.echo("         Fix:  quarto install chrome-headless-shell --no-prompt")
        click.echo("         Or:   matctl doctor --install")
        all_ok = False

    if all_ok:
        click.echo("All checks passed.")
    else:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
