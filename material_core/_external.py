"""Build-time fetch transport for external manuals (REQ-020).

An external manual keeps its authoritative source in a separate public repo
(e.g. `dr-froehlich/devsteward`); `material` commits only a branded wrapper
(`_quarto.yml` + `.gitignore`) and fetches the content at build time from a
pinned ref. This module is the fetch primitive: pure-ish functions plus thin
`subprocess` git wrappers. No `click` dependency — `cli.py` turns the raised
exceptions into `ClickException`.

The fetched entry is renamed to `index.qmd` (rather than `{{< include >}}`-d
from a committed wrapper) so exactly one YAML front-matter block survives the
render. `_`-prefixed fragments and assets copy verbatim as siblings, so their
relative `{{< include _NN-*.qmd >}}` references resolve unchanged.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

# Files the committed wrapper owns — never removed by a --force re-fetch, and
# never treated as fetched content. Mirrors the D2 .gitignore allow-list:
# the Quarto config plus the Typst render-support scaffold (orange-book/,
# assets/) that compose lays down and that is needed to render the manual.
_WRAPPER_KEEP = {"_quarto.yml", ".gitignore", "orange-book", "assets"}
# Brand symlinks created by `matctl link` and build output dirs; left untouched.
_BRAND_LINKS = {"_brand.yml", "brand.scss", "brand-assets", "shared", "_output", ".quarto"}


class ExternalFetchError(Exception):
    """Raised when an external manual cannot be fetched."""


def _git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )


def _shallow_clone(source: str, ref: str, tmp: Path) -> None:
    """Clone `source` at `ref` into `tmp`.

    Tries a shallow branch/tag clone first; falls back to a full clone +
    checkout for a bare sha that `--branch` rejects.
    """
    result = _git(["clone", "--depth", "1", "--branch", ref, source, str(tmp)])
    if result.returncode == 0:
        return
    # Fall back: full clone then checkout (handles bare shas).
    fallback = _git(["clone", source, str(tmp)])
    if fallback.returncode != 0:
        raise ExternalFetchError(
            f"failed to clone {source!r}: {fallback.stderr.strip() or result.stderr.strip()}"
        )
    checkout = _git(["checkout", ref], cwd=tmp)
    if checkout.returncode != 0:
        raise ExternalFetchError(
            f"failed to checkout ref {ref!r} in {source!r}: "
            f"{checkout.stderr.strip()}"
        )


def _resolve_entry(src_subtree: Path, entry: str | None) -> str:
    """Return the top-level entry .qmd filename, explicit or auto-detected."""
    if entry is not None:
        if not (src_subtree / entry).is_file():
            raise ExternalFetchError(
                f"entry {entry!r} not found in fetched subtree {src_subtree}"
            )
        return entry
    candidates = sorted(
        p.name
        for p in src_subtree.glob("*.qmd")
        if not p.name.startswith("_")
    )
    if not candidates:
        raise ExternalFetchError(
            f"no top-level .qmd found in {src_subtree}; set `external.entry`"
        )
    if len(candidates) > 1:
        raise ExternalFetchError(
            f"multiple top-level .qmd files in {src_subtree} "
            f"({', '.join(candidates)}); set `external.entry` to disambiguate"
        )
    return candidates[0]


def _clear_fetched(project_dir: Path) -> None:
    """Remove previously fetched content, preserving the wrapper and symlinks.

    Operates against the D2 allow-list rather than a blind rmtree, so a
    user's committed `_quarto.yml`/`.gitignore` and the brand symlinks
    survive a --force re-fetch.
    """
    keep = _WRAPPER_KEEP | _BRAND_LINKS
    for child in project_dir.iterdir():
        if child.name in keep:
            continue
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)


def _drop_in(src_subtree: Path, project_dir: Path, entry: str) -> None:
    """Copy subtree contents into project_dir, renaming entry → index.qmd."""
    for child in src_subtree.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.copytree(child, project_dir / child.name, dirs_exist_ok=True)
            continue
        target_name = "index.qmd" if child.name == entry else child.name
        shutil.copy2(child, project_dir / target_name)


def fetch_external(
    project_dir: Path,
    *,
    source: str,
    path: str,
    ref: str,
    entry: str | None,
    force: bool,
) -> str | None:
    """Fetch one external manual into project_dir.

    Returns a human-readable summary line on a fetch, or None when skipped
    because content is already present and force is False (idempotent path
    used by `matctl link`). Raises ExternalFetchError on failure.
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    index = project_dir / "index.qmd"
    if index.exists() and not force:
        return None

    if force:
        _clear_fetched(project_dir)

    with tempfile.TemporaryDirectory(prefix="matctl-external-") as tmp_str:
        tmp = Path(tmp_str)
        clone_dir = tmp / "repo"
        _shallow_clone(source, ref, clone_dir)

        src_subtree = clone_dir if path in (".", "") else clone_dir / path
        if not src_subtree.is_dir():
            raise ExternalFetchError(
                f"path {path!r} not found in {source}@{ref}"
            )
        resolved_entry = _resolve_entry(src_subtree, entry)
        _drop_in(src_subtree, project_dir, resolved_entry)

    return (
        f"fetched {project_dir.name} ← {source}@{ref} "
        f"({path}/{resolved_entry} → index.qmd)"
    )
