# REQ-017 Implementation Plan — Wire `slides/brand-assets` into `<project>/slides/`

**Goal:** Add a `<project>/slides/brand-assets` symlink whenever a project has
a `slides/` directory, so the slide-level `logo:` (and any future favicon)
path baked into the rendered HTML resolves at render time and Quarto copies
the asset into `slides/_output/`. Apply at scaffold, retrofit (`matctl link`),
and brand re-seat (`matctl project modify --brand`).

**Context:** Today `material_core/templates/slides/_quarto.yml` carries
`{{LOGO_LINE}}`, which `_brand_resolve.brand_placeholders` substitutes to
`logo: brand-assets/THD-logo.png` (or `logo_pf.svg`, etc.) for non-generic
brands. Quarto bakes that path verbatim into each rendered slide as
`<img src="brand-assets/THD-logo.png" class="slide-logo">`. The browser
resolves that string relative to `slides/_output/01-workflow.html`, requesting
`_output/brand-assets/THD-logo.png` — which Quarto never copied because at
render time there is no `slides/brand-assets/` directory either
(`_brand_resolve.link_project` fans out the four project-root symlinks only).
Theme SCSS escapes this because the slides `_quarto.yml` already references it
as `../brand.scss`, `../shared/base.scss`, which Quarto resolves server-side.
The `logo:` value is the only string that ends up evaluated client-side.

Surfaced 2026-05-21 by rendering `heroes-it-concept/slides/01-workflow.qmd`
end-to-end and observing a 404 for `brand-assets/THD-logo.png` in the preview
server log. Confirmed in headless Chromium against the rendered HTML. Adding
`slides/brand-assets → ../brand-assets` by hand resolved the 404 and the THD
logo appeared. Bug has been silent since `--slides` shipped in REQ-013
(v0.7.0); every existing slides project across every brand is affected.

**Scope boundary:** Symlink wiring only — five touch points in
`_brand_resolve.py` and `cli.py`, plus docs. No template changes, no
`_quarto.yml` rewrites, no `logo:` path changes. The pkg-side
`material_core/brands/<brand>/assets/` layout stays put.

**Status tracking:** `[ ]` open · `[~]` in progress · `[x]` done

---

## Design decisions

### D1 — Minimum-viable wiring: only `slides/brand-assets`

REQ-017 notes leave the choice between minimum-viable
(just `brand-assets`) and full symmetry (`_brand.yml`, `brand.scss`,
`shared/` too) explicitly to the planning step. Decision: **minimum-viable**.

- The slides `_quarto.yml` references `../brand.scss` and
  `../shared/base.scss`. Quarto resolves theme paths server-side relative
  to the project root (where the parent `_quarto.yml` lives), so these
  already work today. No bug — leave alone.
- The only string baked into the rendered HTML and resolved client-side
  is the `logo:` value. That value already uses `brand-assets/...` — the
  fix is to make `slides/brand-assets/...` discoverable to Quarto so it
  copies the asset into `_output/`.
- The symmetry version would only be useful if someone ran
  `quarto preview slides/01-*.qmd` while CWD is `slides/`. No current
  workflow does that, and no requirement asks for it. Defer until a real
  need surfaces.

Trade-off accepted: a future `favicon: brand-assets/...` line in the
slides template would benefit from the same wiring (REQ-017 notes flag
this). The single new symlink solves both.

### D2 — Symlink target: relative `../brand-assets`

```
<project>/slides/brand-assets → ../brand-assets
                                 ↓
                              <project>/brand-assets → <pkg>/brands/<brand>/assets
```

Two-hop chain through the project-root `brand-assets` symlink. Matches
the REQ-017 acceptance text verbatim ("i.e. through the project-root
`brand-assets` symlink → `material_core/brands/<brand>/assets`").

Rationale over a direct absolute symlink:

- Reads clearly in `ls -la`: target is a sibling-relative path, not an
  opaque 7-level absolute package path.
- Survives hand-edits of the project-root `brand-assets` symlink
  (e.g. a user manually pointing it elsewhere) without re-running matctl.
- The full unlink/relink cycle in `relink_project` still tears down and
  rebuilds the slides symlink on `--brand` change (current pattern), so
  there's no functional asymmetry with the four existing symlinks.

### D3 — Gate on `(project_dir / "slides").is_dir()` at link time

`link_project` always creates the four project-root symlinks
unconditionally. The fifth — `slides/brand-assets` — is conditional on
the slides directory existing. Reasons:

- A non-slides project gets nothing new (cleanest possible footprint).
- A slides project gets the symlink automatically the first time
  `link_project` runs after the slides directory appears (true at
  scaffold-with-slides, true at `matctl link --force` on existing slides
  projects).
- If a user later removes `slides/` by hand, the next `link_project`
  run is a no-op for the slides symlink — the stale symlink left behind
  is visible (broken in `ls -la`) and the user will notice. Better than
  silently fixing a state we don't otherwise touch.

Rejected alternative: always create the symlink, accept dangling
broken symlinks in non-slides projects. Noisy and surprising.

### D4 — Unlink detection by path, not target

`unlink_project` currently checks each candidate's target for `"brands"`
or `"shared"` substring. The new slides symlink's target is
`../brand-assets` — fails that check. Detection rule for the new symlink
is the path itself: if `<project_dir>/slides/brand-assets` exists and
`is_symlink()`, remove it. A non-matctl user would not create a symlink
with this name, so false-positive risk is negligible. Same logic as
treating the path `<project>/_brand.yml` as a managed slot — even though
the existing code over-engineers that check via target inspection.

### D5 — `project modify --slides` (false→true) wires the new symlink

`project_modify`'s `--slides` true branch creates the slides directory
from the overlay and runs `substitute_placeholders`. It does **not**
currently call `link_project` afterward (because the four project-root
symlinks already exist). Post-REQ-017, it must call `link_project` again
so the new slides-side symlink gets wired.

The call is idempotent for the four project-root symlinks (existing
ones are skipped without `force`). Only the new `slides/brand-assets`
is materially added. Cleanest path: call `link_project` unconditionally
in this branch — fewer code paths to reason about than a dedicated
"slides-only" helper.

### D6 — No test coverage committed, manual acceptance is the contract

Consistent with REQ-004..016. Acceptance maps directly to REQ-017
§Acceptance criteria.

---

## Phase 1 — `_brand_resolve.py` link/unlink

All edits in `material_core/_brand_resolve.py`.

- [x] **1.1** Extend `link_project` to create
      `<project_dir>/slides/brand-assets → ../brand-assets` when
      `(project_dir / "slides").is_dir()`. Reuse the existing
      broken/exists/force handling pattern (no new helper). Use a
      relative `Path("../brand-assets")` for `symlink_to`.
- [x] **1.2** Extend `unlink_project` to remove
      `<project_dir>/slides/brand-assets` if it exists and
      `is_symlink()`. No target check — the path itself is the marker.
      Place this after the existing `_BRAND_SYMLINKS` loop, not inside
      it (the loop iterates project-root names; the slides symlink is
      a nested path, not a name).
- [x] **1.3** Update the module docstring to list five symlinks, with
      the fifth (slides/brand-assets) explicitly called out as
      "created only when `slides/` exists; target is the relative
      `../brand-assets` so it chains through the project-root symlink".

## Phase 2 — CLI: wire link into `--slides` false→true

All edits in `material_core/cli.py`.

- [x] **2.1** In `project_modify`'s `--slides` true branch
      (~lines 1062–1083), after `_overlay_copy` and the
      `substitute_placeholders` call, add a call to
      `link_project(dest, proj_brand, _package_root())`. No `force=`
      (the four root symlinks already exist and should be preserved).
- [x] **2.2** Inspect — but do **not** alter — the existing
      `link`/`unlink` commands and `compose()`. Both already route
      through `link_project`/`unlink_project`/`relink_project`, so
      Phase 1 changes propagate without further wiring:
      - `matctl link` (root mode) iterates entries and calls
        `link_project` for each (cli.py:1201).
      - `matctl link` (project-dir mode) calls `link_project` for cwd
        (cli.py:1213).
      - `matctl unlink` calls `unlink_project` per project
        (cli.py:1255, 1260).
      - `compose()` calls `link_project` as Step 6 (_compose.py:155).
      - `project_modify --brand` calls `relink_project` (cli.py:1056),
        which is `unlink_project` + `link_project`.

## Phase 3 — Documentation

- [x] **3.1** `CLAUDE.md` matctl section: update the `matctl link`
      bullet to mention the conditional fifth symlink for slides
      projects. Add a one-line note in the Current-status entry for
      REQ-017 at release time (next to the existing v0.8.9 entry).
- [x] **3.2** `material_core/_brand_resolve.py` module docstring:
      already touched in 1.3 — confirm the wording matches CLAUDE.md.
- [x] **3.3** Tick acceptance criteria in
      `docs/requirements/REQ-017.md`, set `Status: DONE`, fill
      `Completed`, update `REQUIREMENTS_INDEX.md`.

## Phase 4 — Release

- [x] **4.1** Bump `pyproject.toml` to `v0.9.0`. Minor: the symlink
      topology is observably different to users and requires
      `matctl link --force` to retrofit existing slides projects. No
      breaking API change, but visible enough to warrant a minor
      bump rather than a patch.
- [ ] **4.2** Tag `v0.9.0`, push the tag.
- [ ] **4.3** Update `material/.github/workflows/publish.yml` pinned
      version to `v0.9.0`.
- [ ] **4.4** Release notes call out: "Existing slides projects need
      `matctl link --force` after upgrade to pick up the new
      `slides/brand-assets` symlink. Without it, slides continue to
      render without a logo image (the pre-fix state)."

## Phase 5 — `material/` retrofit

Single commit in the `material/` repo.

- [ ] **5.1** Upgrade `material-core` (pinned tag bump from 5.3 lands
      in CI; for local: `pipx install --force --editable
      /home/peter/projects/material-core`).
- [ ] **5.2** `matctl link --force` at the repo root. Verify that
      every project with a `slides/` directory now has
      `slides/brand-assets` as a symlink (find with
      `find . -maxdepth 3 -path '*/slides/brand-assets'`).
- [ ] **5.3** Render `heroes-it-concept` end-to-end (the project that
      surfaced the bug). Inspect the rendered HTML for the brand logo
      image and confirm no 404 for `brand-assets/*` in the
      `quarto preview` server log.
- [ ] **5.4** Commit the new symlinks to `material/` — the repo
      already commits its other project-root brand symlinks, so the
      slides one follows the same pattern.

---

## Manual acceptance run (maps to REQ-017 §Acceptance criteria)

Run in a throwaway `material` checkout against the editable
`material-core` install.

- [ ] **A1** `matctl project add slides-test --structure chapters
      --slides --brand thd --lang de --title "Slides Test"` — verify
      `slides-test/slides/brand-assets` exists, `is_symlink()`,
      `os.readlink(...)` returns `../brand-assets`, and the resolved
      path is `material_core/brands/thd/assets`.
- [ ] **A2** Inside `slides-test/`, delete `slides/brand-assets` then
      run `matctl link --force`. Verify it reappears with the same
      target.
- [ ] **A3** Repeat A2 from the repo root (`matctl link --force`).
- [ ] **A4** `matctl unlink` inside `slides-test/` — verify
      `slides/brand-assets` is removed along with the four
      project-root symlinks.
- [ ] **A5** `matctl link --force` to re-wire, then
      `matctl project modify slides-test --brand pf` — verify
      `slides/brand-assets` still exists with the same `../brand-assets`
      target, and the project-root `brand-assets` now resolves into
      `brands/pf/assets`.
- [ ] **A6** `quarto render slides-test` then confirm
      `slides-test/slides/_output/brand-assets/THD-logo.png` (or
      `logo_pf.svg` after A5) exists. Optionally `quarto preview`
      and watch for `brand-assets/*` 404s in the server log — their
      absence is the signal.
- [ ] **A7** `matctl project add generic-slides-test --structure
      single --slides --brand generic --lang de --title "Generic"` —
      `slides/brand-assets` symlink is still created (resolves to the
      empty `brands/generic/assets/`), and the rendered HTML has no
      `<img class="slide-logo">` element because
      `brand_placeholders("generic")` emits an empty `LOGO_LINE`.
      No 404 either (no asset requested).
- [ ] **A8** `quarto preview heroes-it-concept` in the `material`
      checkout after Phase 5 retrofit — confirm the THD logo appears
      bottom-right on every slide and the preview server log shows
      no `brand-assets/*` 404.
- [ ] **A9** `matctl project add no-slides-test --structure single
      --no-slides --brand thd --lang de --title "No Slides"` —
      confirm no `slides/` directory exists and no
      `slides/brand-assets` symlink is created.
- [ ] **A10** `grep -n "slides/brand-assets" material_core/_brand_resolve.py
      CLAUDE.md` — both surfaces mention the new symlink. Wording
      consistent.
- [ ] **A11** `matctl project modify no-slides-test --slides` —
      slides overlay added, and `no-slides-test/slides/brand-assets`
      symlink is now present (Phase 2 wiring).

---

## Commit strategy

`material-core`:

1. **Phase 1 + 2** — single commit. `_brand_resolve.py` link/unlink
   extension + cli.py `--slides` true wiring. Self-contained;
   nothing renders differently until the user runs `matctl link
   --force`, so no broken in-between state.
2. **Phase 3** — docs commit. CLAUDE.md, REQ-017 status,
   REQUIREMENTS_INDEX.md.
3. **Phase 4** — version bump + tag (separate so the diff is one
   line).

`material`:

- One migration commit per Phase 5: the new `slides/brand-assets`
  symlinks across every slides project, plus the
  `.github/workflows/publish.yml` version-pin bump.

## Risks and mitigations

- **`slides/brand-assets` pre-exists as a regular file or directory.**
  Without `--force`, `link_project` skips it (existing behaviour). With
  `--force`, it deletes and replaces — same contract as the four
  project-root symlinks. Acceptable; users who manually created such
  a file are doing something unusual and would expect matctl to win.
- **Empty `slides/` directory.** Phase 1.1 gates on `is_dir()`, which
  is true for an empty directory. Symlink still gets created. Harmless
  — an empty slides directory is itself an anomaly the user should
  clean up, and the extra symlink is no worse than the existing four
  in such a project.
- **Retrofit timing.** Until the user runs `matctl link --force`
  after upgrading, existing slides projects render without logos —
  exactly the pre-fix state, no regression. Release notes flag this.
- **`generic` brand has an empty `brands/generic/assets/`.** The new
  symlink resolves to an empty directory — fine. Slides template's
  `{{LOGO_LINE}}` is empty for generic, so no asset is referenced.
  Phase A7 verifies.
- **Quarto's `_output/` cache.** A previously rendered slides
  project may still have a stale `_output/` from before the fix.
  `quarto render` rewrites it; `quarto preview` may need a hard
  refresh. Not specific to this fix; documented under
  CLAUDE.md's preview troubleshooting.
- **Future favicon path in slides template.** REQ-017 notes mention
  that `favicon: brand-assets/...` would have the same bug. The
  single new symlink fixes both — no extra work needed if/when the
  slides template adds a favicon line.

## Explicitly out of scope

- Wiring `slides/_brand.yml`, `slides/brand.scss`, `slides/shared/`
  (D1). Defer until a workflow exercises `quarto preview` from
  inside `slides/`.
- Changing the slides `_quarto.yml` `logo:` path to
  `../brand-assets/...` (REQ-017 Non-goals). The browser cannot
  reach above `_output/`; only Quarto-side resource copying
  resolves this, and that requires the file to be discoverable at
  the slides-side path Quarto sees.
- Restructuring brand-asset storage in the package (REQ-017
  Non-goals).
- An automated CI lint that detects "HTML-baked path doesn't
  resolve" (e.g. by running a real render in CI and scraping the
  preview server log for 404s). Manual acceptance is the contract
  for now; a CI lint can come as a follow-up when there's a second
  similar bug.
- Backwards-compatibility shim for slides projects scaffolded
  pre-v0.9.0 — Phase 5's `matctl link --force` is the one-time
  retrofit; no rolling deprecation needed (single-user repo).
