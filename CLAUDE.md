# material-core — Claude Code Guide

## What this repo is

Engineering tooling for the [`material`](https://github.com/pfroehlich/material)
content repository: the `matctl` Python CLI, shared branding (`_brand.yml`,
`shared/`), the Cloudflare access Worker, the course scaffolder template, and
all engineering documentation.

`material-core` is consumed by `material` via a pinned git tag — no PyPI
release. Local development uses an editable `pipx` install so SCSS/brand edits
are visible to `quarto preview` in `material` without any sync step.

Scope boundary: **no lecture content lives here.** Content — chapters, slides,
assets for specific courses — belongs in `material/`.

## Repository layout

```
material-core/
  pyproject.toml               — package metadata, matctl entry point
  material_core/
    cli.py                     — matctl commands
    _brand.yml                 — brand file shipped as package data
    shared/                    — SCSS, fonts, logo, diagram assets
    cloudflare/worker.js       — token-validating access Worker
    scripts/manage-tokens.sh   — KV token CRUD (REQ-002 will fold into matctl)
    templates/course/          — scaffolding template (was _template/ in vorlesungen)
  docs/
    administration.md          — ops reference (arch, deploy, tokens)
    authoring.md               — Quarto authoring reference for content authors
    plans/                     — implementation plans (e.g. req-001-repo-split.md)
    requirements/              — requirements tracking (see Requirements_Management.md)
```

## matctl CLI

- `matctl link` — symlink `_brand.yml` and `shared/` from this package into the
  current working directory. Intended to be run from inside a `material`
  checkout. With `pipx install --editable`, symlinks resolve into the live
  source tree, so SCSS edits are immediately visible to `quarto preview`.
- `matctl unlink` — remove the symlinks.
- `matctl course add <name> [--title "..."] [--subtitle "..."]` — scaffold a
  new course from the template and register it in `projects.yml`.
- `matctl course remove <name> [--yes]` — remove the course directory and
  manifest entry (remote content and KV tokens must be cleaned up manually).

## How this repo is consumed

CI (pinned):

```bash
pipx install "git+https://github.com/pfroehlich/material-core@v0.2.0"
matctl link
quarto render <course>
```

Local development (editable):

```bash
pipx install --editable /home/peter/projects/material-core
cd /home/peter/material     # formerly vorlesungen
matctl link
quarto preview <course>     # picks up live shared/base.scss edits
```

## Requirements tracking

New requirements, plans, and status changes live in `docs/requirements/` and
`docs/plans/` of *this* repo — not in `material/`. Follow the workflow in
[`docs/requirements/Requirements_Management.md`](docs/requirements/Requirements_Management.md);
read [`REQUIREMENTS_INDEX.md`](docs/requirements/REQUIREMENTS_INDEX.md) at
session start.

## Release flow

1. Commit to `main`.
2. Tag `vX.Y.Z`, push the tag.
3. Update the pinned version in `material/.github/workflows/publish.yml`.

Semver: breaking CLI or brand-contract changes bump major; new commands or
assets bump minor; fixes bump patch.

## Current status

REQ-001 DONE. REQ-003 DONE. REQ-004 DONE (`matctl course add/remove`). REQ-005 OPEN (standalone doc support — shares `_projects.py`/`_scaffold.py` from REQ-004). REQ-006 OPEN (`matctl token issue/list/revoke/show` — port of `manage-tokens.sh` to Python, adds `httpx`).
