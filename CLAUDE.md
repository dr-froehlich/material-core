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
    scripts/.env               — Cloudflare credentials (gitignored; read by matctl token)
    templates/course/          — course scaffolding template
    templates/doc/             — standalone document scaffolding template
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
- `matctl group add <name> --title "..."` — register a new group in
  `projects.yml`. No directory created. Groups must exist before any course or
  doc can reference them via `--group`.
- `matctl group remove <name> [--yes]` — remove a group entry (fails if any
  course/doc still references it).
- `matctl group modify <name> --title "..."` — update the group's title in the
  manifest.
- `matctl course add <name> [--title "..."] [--subtitle "..."] [--group <name>]`
  — scaffold a new course from the template and register it in `projects.yml`.
  `--title` is recorded in the manifest (defaults to title-cased slug). `--group`
  requires the group to already exist; the project deploys under `<group>/<name>/`
  and shares access scope with other group members.
- `matctl course remove <name> [--yes]` — remove the course directory and
  manifest entry (remote content and KV tokens must be cleaned up manually).
- `matctl course modify <name> [--title "..."] [--group <name>]` — update a
  course's title (write-through to `_quarto.yml:book.title`) and/or group. Pass
  `--group ""` to remove grouping. At least one flag required.
- `matctl doc add <name> [--title "..."] [--group <name>]` — scaffold a new
  standalone document (single `index.qmd`, no slides) and register it in
  `projects.yml`. `--title` and `--group` behave as for `course add`.
- `matctl doc remove <name> [--yes]` — remove the document directory and
  manifest entry (remote content must be cleaned up manually).
- `matctl doc modify <name> [--title "..."] [--group <name>]` — update a
  document's title (write-through to `index.qmd` front matter) and/or group.
  Behaves analogously to `course modify`.
- `matctl token issue <course> <label> [--days 365]` — generate a token, write
  it to Cloudflare KV, and print the ready-to-paste iLearn URL.
- `matctl token list [<course>]` — table of all tokens (or filtered to one
  course); expired tokens flagged `[EXPIRED]`.
- `matctl token revoke <token>` — delete the KV entry; effect is immediate at
  the Worker.
- `matctl token show <token>` — pretty-print the raw KV JSON for one token.

## How this repo is consumed

CI (pinned):

```bash
pipx install "git+https://github.com/pfroehlich/material-core@v0.5.0"
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

REQ-001 DONE. REQ-003 DONE. REQ-004 DONE (`matctl course add/remove`). REQ-005 DONE (`matctl doc add/remove` + doc template). REQ-006 DONE (`matctl token issue/list/revoke/show` — replaced `manage-tokens.sh`). REQ-007 DONE (group scope: `--group` flag, scope-based Worker authorization, grouped deploy paths). REQ-008 DONE (group lifecycle, titles in manifest, `modify` subcommands).
