"""matctl — command-line interface for material-core."""

from __future__ import annotations

import json
import re
import secrets
import shutil
from datetime import date, timedelta
from importlib.resources import files
from pathlib import Path

import click

from ruamel.yaml import YAML

from ._cloudflare import KVClient, load_credentials
from ._landing import regenerate_group
from ._projects import (
    PROJECTS_FILE,
    add_group,
    add_project,
    dependents_of_group,
    find_entry,
    group_exists,
    load_manifest,
    project_names,
    remove_group,
    remove_project,
    save_manifest,
)
from ._scaffold import (
    copy_template,
    substitute_placeholders,
    title_case_from_slug,
)

SITE_BASE = "https://material.professorfroehlich.de"

LINK_TARGETS = ("_brand.yml", "shared")

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


def _scaffold_project(
    project_type: str,
    template_subdir: str,
    name: str,
    title: str,
    placeholders: dict[str, str],
    next_steps: list[str],
    group: str | None = None,
) -> None:
    """Validate, copy template, substitute placeholders, patch manifest, echo."""
    if not _NAME_RE.fullmatch(name):
        raise click.ClickException(
            f"invalid {project_type} name {name!r}: must match [a-z0-9][a-z0-9._-]*"
        )
    if group is not None and not _NAME_RE.fullmatch(group):
        raise click.ClickException(
            f"invalid group name {group!r}: must match [a-z0-9][a-z0-9._-]*"
        )
    cwd = Path.cwd()
    manifest_path = cwd / PROJECTS_FILE
    manifest = load_manifest(manifest_path)
    if name in project_names(manifest):
        raise click.ClickException(
            f"{name} already registered in {PROJECTS_FILE}"
        )
    if group is not None and not group_exists(manifest, group):
        raise click.ClickException(
            f"group {group!r} not found in {PROJECTS_FILE} — "
            f"create it first with `matctl group add {group} --title ...`"
        )
    dest = cwd / name
    if dest.exists():
        raise click.ClickException(f"{dest} already exists")

    copy_template(template_subdir, dest)
    substitute_placeholders(dest, placeholders)
    add_project(manifest, name, project_type, title, group=group)
    save_manifest(manifest_path, manifest)
    _regenerate_affected_groups(manifest, group)

    click.echo(f"created {project_type} {name}")
    click.echo("next steps:")
    for step in next_steps:
        click.echo(f"  {step}")


def _remove_project(label: str, name: str, yes: bool) -> None:
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
@click.option(
    "--group",
    default=None,
    help="Optional URL-path group; deploys under <group>/<name>/.",
)
def course_add(
    name: str, title: str | None, subtitle: str, group: str | None
) -> None:
    """Scaffold a new course and register it in projects.yml."""
    resolved_title = title or title_case_from_slug(name)
    _scaffold_project(
        "course",
        "course",
        name,
        resolved_title,
        {
            "{{COURSE_NAME}}": name,
            "{{COURSE_TITLE}}": resolved_title,
            "{{COURSE_SUBTITLE}}": subtitle,
        },
        [
            f"quarto preview {name}",
            f"git add {name}/ {PROJECTS_FILE}",
            f"git commit -m 'Add course: {name}'",
            "git push",
        ],
        group=group,
    )


@course.command("remove")
@click.argument("name")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
def course_remove(name: str, yes: bool) -> None:
    """Remove a course from the manifest and delete its directory."""
    _remove_project("course", name, yes)


@main.group()
def doc() -> None:
    """Manage standalone documents in a material checkout."""


@doc.command("add")
@click.argument("name")
@click.option(
    "--title",
    default=None,
    help="Human-readable title (default: <name> title-cased).",
)
@click.option(
    "--group",
    default=None,
    help="Optional URL-path group; deploys under <group>/<name>/.",
)
def doc_add(name: str, title: str | None, group: str | None) -> None:
    """Scaffold a new standalone document and register it in projects.yml."""
    resolved_title = title or title_case_from_slug(name)
    _scaffold_project(
        "doc",
        "doc",
        name,
        resolved_title,
        {
            "{{DOC_NAME}}": name,
            "{{DOC_TITLE}}": resolved_title,
        },
        [
            f"quarto preview {name}",
            f"git add {name}/ {PROJECTS_FILE}",
            f"git commit -m 'Add doc: {name}'",
            "git push",
        ],
        group=group,
    )


@doc.command("remove")
@click.argument("name")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
def doc_remove(name: str, yes: bool) -> None:
    """Remove a standalone document from the manifest and delete its directory."""
    _remove_project("document", name, yes)


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


def _rewrite_title(label: str, dest: Path, new_title: str) -> None:
    """Write-through the new title into the scaffolded file for this type."""
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    if label == "course":
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

    if label == "doc":
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
        import io
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

    raise click.ClickException(f"unknown label for title rewrite: {label}")


def _modify_project(
    label: str,
    name: str,
    title: object,
    group: object,
) -> None:
    """Shared implementation for `course modify` and `doc modify`."""
    if title is _UNSET and group is _UNSET:
        raise click.UsageError("specify --title and/or --group")

    cwd = Path.cwd()
    manifest_path = cwd / PROJECTS_FILE
    manifest = load_manifest(manifest_path)
    entry = find_entry(manifest, name)
    if entry is None:
        raise click.ClickException(
            f"{name} not found in {PROJECTS_FILE}"
        )
    actual_type = entry.get("type")
    if actual_type != label:
        raise click.ClickException(
            f"{name} is a {actual_type!r}, not a {label!r}"
        )

    old_group = entry.get("group")
    changes: list[str] = []
    group_changed = False

    if title is not _UNSET:
        if not isinstance(title, str) or title == "":
            raise click.ClickException("--title must not be empty")
        entry["title"] = title
        dest = cwd / name
        _rewrite_title(label, dest, title)
        changes.append(f"title → {title!r}")

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
                    f"invalid group name {group!r}: "
                    "must match [a-z0-9][a-z0-9._-]*"
                )
            if not group_exists(manifest, group):
                raise click.ClickException(
                    f"group {group!r} not found in {PROJECTS_FILE} — "
                    f"create it first with `matctl group add {group} --title ...`"
                )
            entry["group"] = group
            changes.append(f"group → {group!r}")
            group_changed = True

    save_manifest(manifest_path, manifest)

    if group_changed:
        _regenerate_affected_groups(manifest, old_group, entry.get("group"))
    else:
        _regenerate_affected_groups(manifest, old_group)

    click.echo(f"modified {label} {name}: {', '.join(changes)}")
    if group_changed:
        click.echo(
            "note: remote content at the old deploy path on "
            "material.professorfroehlich.de is NOT moved by this command — "
            "it will become stale on the next CI run and must be cleaned up "
            "manually. See docs/administration.md."
        )


@course.command("modify")
@click.argument("name")
@click.option(
    "--title",
    default=_UNSET,
    type=click.UNPROCESSED,
    help="New human-readable title (write-through to _quarto.yml).",
)
@click.option(
    "--group",
    default=_UNSET,
    type=click.UNPROCESSED,
    help="New group (must exist); pass empty string to remove grouping.",
)
def course_modify(name: str, title: object, group: object) -> None:
    """Modify a course's title and/or group."""
    _modify_project("course", name, title, group)


@doc.command("modify")
@click.argument("name")
@click.option(
    "--title",
    default=_UNSET,
    type=click.UNPROCESSED,
    help="New human-readable title (write-through to index.qmd front matter).",
)
@click.option(
    "--group",
    default=_UNSET,
    type=click.UNPROCESSED,
    help="New group (must exist); pass empty string to remove grouping.",
)
def doc_modify(name: str, title: object, group: object) -> None:
    """Modify a document's title and/or group."""
    _modify_project("doc", name, title, group)


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


if __name__ == "__main__":
    main()
