# REQ-001 Implementation Plan — Repository Split

**Goal:** Separate the current `vorlesungen` monorepo into `material-core`
(tooling, versioned) and `material` (content, the renamed current repo) without
requiring a `material-core` re-release for everyday SCSS or brand tweaks during
local preview.

**Context:** Nothing on `material.professorfroehlich.de` is in productive use
yet — only test material is published. There are no students depending on
uptime, so the plan does not need to preserve continuous deployability across
the migration. Brief breakage is fine; rollback machinery is unnecessary.

**Status tracking:** `[ ]` open · `[~]` in progress · `[x]` done

---

## Design decision — how `material-core` delivers `_brand.yml` + `shared/` to `material`

This is the only non-obvious piece. Three options were considered:

| Option | Local-preview ergonomics | CI ergonomics | Verdict |
|---|---|---|---|
| **A. Git submodule** (`material/.material-core/` pinned to a tag) | Edits require `cd` into the submodule; pointer churn on every shared-asset tweak | Standard `git submodule update` | Rejected — submodule chores are exactly the kind of friction the split is supposed to remove |
| **B. Build-time copy** (`matctl sync` copies package data into `material/`) | Re-run `matctl sync` after every SCSS edit before previewing — kills live reload | Trivial in CI | Rejected — violates the live-preview constraint |
| **C. Symlinks managed by `matctl`** (`matctl link` symlinks `_brand.yml` and `shared/` to the installed package's data dir) | With `pip install -e ../material-core`, symlinks resolve to the live source tree → SCSS edits are instantly visible to `quarto preview` | `pip install material-core@<tag>` then `matctl link` | **Chosen** |

**How Option C works:**

- `material-core` is a Python package. `_brand.yml` and `shared/` ship as
  package data (declared in `pyproject.toml` under
  `[tool.setuptools.package-data]` or equivalent).
- `matctl link` resolves the installed package location
  (`importlib.resources.files("material_core")`) and creates two symlinks in
  the current working directory:
  - `./_brand.yml` → `<pkg>/_brand.yml`
  - `./shared` → `<pkg>/shared`
- Both symlinks are gitignored in `material/`.
- Local dev: `pipx install -e ../material-core` (or `pip install -e` inside a
  venv). Symlinks transitively resolve to the live `material-core` checkout,
  so `quarto preview` picks up SCSS edits with no rebuild step.
- CI: `pipx install "git+https://github.com/<user>/material-core@v1.0.0"`,
  then `matctl link`, then `quarto render`. The symlink targets sit inside the
  pipx venv — read-only, version-pinned, reproducible.
- `matctl unlink` removes the symlinks (used by CI cleanup; rarely needed
  locally).

**Why this is safe:**

- Symlinks are POSIX-native and behave identically on WSL2 and the Linux GHA
  runner. The project is single-user and Linux-only; Windows-native checkouts
  are not a constraint.
- Quarto resolves `_brand.yml` and `shared/base.scss` through the symlink
  exactly as it does for in-tree files; no special path handling.
- `material/.gitignore` lists `_brand.yml` and `shared/` so an accidental
  `git add` cannot drift them back into the content repo.

---

## Phase 1 — Create `material-core` skeleton  *(local, no GitHub yet)*

- [ ] **1.1** Create empty directory `~/material-core/` as a sibling of `~/vorlesungen/`.
- [ ] **1.2** Initialize git, add `pyproject.toml` declaring:
  - Package name `material_core`, CLI entry point `matctl = material_core.cli:main`
  - Python ≥3.11
  - Package data: `_brand.yml`, `shared/**`, `cloudflare/**`, `templates/**`
  - Dependencies: `click` (or `typer`), nothing exotic yet
- [ ] **1.3** Stub `material_core/cli.py` with two real commands:
  - `matctl link` — create the two symlinks described above
  - `matctl unlink` — remove them
  - Stubs for `matctl render`, `matctl deploy`, `matctl new` (just `raise NotImplementedError` — REQ-002 territory, but the entry points need to exist so CI can call them)
- [ ] **1.4** Editable install in a throwaway venv, run `matctl link` in an empty test dir, confirm symlinks resolve.

## Phase 2 — Populate `material-core` with tooling

Straight copies — no history rewriting, no `git filter-repo` (see REQ-001 notes).

- [ ] **2.1** Copy from `vorlesungen/` into `material-core/`:
  - `_brand.yml` → `material_core/_brand.yml`
  - `shared/` → `material_core/shared/`
  - `cloudflare/worker.js` → `material_core/cloudflare/worker.js`
  - `scripts/manage-tokens.sh` → `material_core/scripts/manage-tokens.sh` (rewrite as `matctl tokens` later in REQ-002)
  - `new-course.sh` → discard; replaced by `matctl new` in REQ-002
  - `_template/` → `material_core/templates/course/`
  - `docs/administration.md`, `docs/authoring.md`, `docs/plans/`, `docs/requirements/` → `material-core/docs/`
- [ ] **2.2** Write `material-core/CLAUDE.md` describing the engineering scope.
- [ ] **2.3** Minimal `README.md` with install + `matctl link` instructions.

## Phase 3 — Push `material-core` and tag `v0.1.0`

- [ ] **3.1** Create GitHub repo `material-core`, push `main`.
- [ ] **3.2** Tag `v0.1.0` and push the tag.
- [ ] **3.3** Sanity check: `pipx install "git+https://github.com/<user>/material-core@v0.1.0"` from a clean shell, run `matctl link` in a temp dir, confirm symlinks resolve.

## Phase 4 — Strip tooling out of `vorlesungen`

Work directly on `dev`. No protection branch needed.

- [ ] **4.1** Delete from the working tree:
  - `_brand.yml`, `shared/`
  - `cloudflare/`, `scripts/`, `new-course.sh`
  - `_template/`
  - `docs/administration.md`, `docs/authoring.md`, `docs/plans/`, `docs/requirements/`
- [ ] **4.2** `.gitignore`: add `_brand.yml`, `/shared`, `__pycache__/`.
- [ ] **4.3** Rewrite `CLAUDE.md` for content-only scope. Point to `material-core` for tooling docs.
- [ ] **4.4** Replace `.github/workflows/publish.yml` with a thin delegating workflow:
  - Checkout
  - `pipx install "git+https://github.com/<user>/material-core@v0.1.0"`
  - `matctl link`
  - Loop over courses calling `quarto render` (carry the existing logic forward verbatim — `matctl render` arrives in REQ-002)
  - The existing `sshpass`+`scp` deploy block, copied verbatim
  - Path filters via `dorny/paths-filter` retained

## Phase 5 — Local end-to-end check

- [ ] **5.1** In `~/vorlesungen`: `matctl link`, then `quarto render digital-und-mikrocomputertechnik`. Eyeball HTML, PDF, slides — looks right is good enough. No byte-diff against an old build is needed.
- [ ] **5.2** Edit `~/material-core/material_core/shared/base.scss` (e.g. change a color), run `quarto preview` in `~/vorlesungen`, confirm the change is visible without re-installing or re-linking. **This is the only check that actually validates the design choice — don't skip it.**

## Phase 6 — Rename `vorlesungen` → `material` and ship

- [ ] **6.1** Merge `dev` → `main` in `vorlesungen`. Let CI run; fix anything that breaks. (No users are affected if the build is briefly red.)
- [ ] **6.2** GitHub web UI: rename `vorlesungen` repo to `material`.
- [ ] **6.3** Local: `git remote set-url origin git@github.com:<user>/material.git`, `git fetch`.
- [ ] **6.4** Smoke-test the deployed site: `material.professorfroehlich.de/digital-und-mikrocomputertechnik/` loads and looks correct.

## Phase 7 — Token sanity check

- [ ] **7.1** Issue, validate, and revoke a throwaway token against the unchanged Worker + KV. Confirms the access path is unaffected by the split.

## Phase 8 — Close out REQ-001

- [ ] **8.1** Tick acceptance criteria in `material-core/docs/requirements/REQ-001.md`, set status `DONE`, fill `Completed` and `Verified by`.
- [ ] **8.2** Update `REQUIREMENTS_INDEX.md` in `material-core` to match.
- [ ] **8.3** From here on, new requirements are authored in `material-core`.

---

## Open questions deferred to REQ-002

- Final shape of `matctl render` / `matctl deploy` (matrix CI, change detection, format selection). Until then, the workflow uses the old `quarto render` loop verbatim.
- Whether `manage-tokens.sh` becomes `matctl tokens` immediately or stays a shell script in `material-core/scripts/`.
- Whether `_template/` lives under `material_core/templates/course/` (current proposal) or as a separate repo.
