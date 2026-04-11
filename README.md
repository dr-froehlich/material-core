# material-core

Tooling for the [`material`](https://github.com/pfroehlich/material) lecture
and publication content repository: brand assets, shared SCSS, the Cloudflare
Worker source, course scaffolding, and the `matctl` CLI.

This repo is consumed by `material` via a pinned git tag — there is no PyPI
release. Local development uses an editable install so that SCSS edits are
visible to `quarto preview` without re-installing.

## Install

CI / pinned consumption:

```bash
pipx install "git+https://github.com/pfroehlich/material-core@v0.1.0"
```

Local development (editable, picks up live edits):

```bash
pipx install --editable /home/peter/projects/material-core
```

## Usage

Inside a `material` checkout (or any directory that needs the brand assets):

```bash
matctl link     # creates ./_brand.yml and ./shared symlinks into the package
matctl unlink   # removes them
```

`matctl render`, `matctl deploy`, and `matctl new` are stubs reserved for
REQ-002.

## Repository contents

- `material_core/` — Python package (CLI + brand/shared assets as package data)
- `material_core/cloudflare/worker.js` — token-validating access Worker
- `material_core/scripts/manage-tokens.sh` — KV token CRUD helper
- `material_core/templates/course/` — course scaffolding template
- `docs/` — engineering documentation (administration, authoring, plans, requirements)

See [`CLAUDE.md`](CLAUDE.md) for the full engineering guide.

## Status

REQ-001 (repository split) in progress.
