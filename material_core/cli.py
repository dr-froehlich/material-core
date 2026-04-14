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

from ._cloudflare import KVClient, load_credentials
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

SITE_BASE = "https://material.professorfroehlich.de"

LINK_TARGETS = ("_brand.yml", "shared")

_NAME_RE = re.compile(r"[a-z0-9][a-z0-9._-]*")


def _package_root() -> Path:
    return Path(str(files("material_core")))


def _scaffold_project(
    project_type: str,
    template_subdir: str,
    name: str,
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
    dest = cwd / name
    if dest.exists():
        raise click.ClickException(f"{dest} already exists")

    copy_template(template_subdir, dest)
    substitute_placeholders(dest, placeholders)
    add_project(manifest, name, project_type, group=group)
    save_manifest(manifest_path, manifest)

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


if __name__ == "__main__":
    main()
