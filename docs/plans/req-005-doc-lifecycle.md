# REQ-005 Implementation Plan — `doc` template and `matctl doc add` / `doc remove`

**Goal:** Add a second project type (`doc`) that mirrors `course` but
produces a single-file Quarto project — no book profile, no chapters, no
slides — and ship the lifecycle commands to scaffold and remove it:

```
matctl doc add <name> [--title "Human readable title"]
matctl doc remove <name> [--yes]
```

**Context:** REQ-003 declared `type: course | doc` in `projects.yml` and the
matrix workflow already has the `doc` rendering and deploy branch wired up
(`publish.yml:150–157, 181–184`). REQ-004 landed `course add/remove` and
factored the placeholder substitution and manifest patching into private
helpers (`material_core/_scaffold.py`, `material_core/_projects.py`)
explicitly so REQ-005 could share them. REQ-005 is the first requirement to
exercise the `doc` branch end-to-end.

**Scope boundary:** Mechanism only — template, CLI, shared helper, docs,
release. The motivating real-world `esp-survival-guide` migration is the
acceptance vehicle for the CI matrix end-to-end criterion (phase 7). It is
not new content work; the file already exists at
`material/digital-und-mikrocomputertechnik/esp-survival-guide.qmd`, having
been moved out of the `chapters/` subdir in preparation.

**Naming note (not in this requirement):** A future requirement may rename
`course` → `book` and `doc` → `article` for cleaner semantics. **Do not
make that rename here.** REQ-005 ships with the names already declared in
REQ-003 / REQ-004 to keep the diff focused; the rename is a separate
breaking change with its own migration plan and major version bump.

**Status tracking:** `[ ]` open · `[~]` in progress · `[x]` done

---

## Design decisions

**D1 — Shared scaffolder helper, not duplicated logic.**
`course add` and `doc add` both validate the name, load the manifest, check
for duplicates, copy a template, substitute placeholders, append a manifest
entry, and echo next steps. The differences are: template subdirectory,
manifest `type:` value, set of placeholders, and the next-steps message.
Extract `_scaffold_project(...)` into `cli.py` (private function, not a new
module — small enough that a third file is overkill). Click commands stay
as thin wrappers.

**D2 — Same approach for remove.**
`course remove` and `doc remove` differ only in the noun used in error
messages and notes. Extract `_remove_project(label, name, yes)` similarly.

**D3 — Doc template is flat, no `_shared/`, no `slides/`.**
A doc is one `index.qmd` plus an `assets/` folder. Brand styling comes via
the same `../shared/base.scss` and `../shared/typst-show.typ` paths courses
use, since `matctl link` puts `shared/` at the repo root either way.

**D4 — Output dir is `_output/`, not `_output/book/`.**
Per REQ-005 notes: docs use a flat `_output/` so the Netcup deploy path
stays one level shallower. The workflow's doc branch already expects this.

**D5 — Placeholders use `{{DOC_NAME}}` / `{{DOC_TITLE}}` (not reusing
`COURSE_*`).** Keeps templates self-documenting and prevents accidental
cross-contamination if a placeholder set ever diverges.

**D6 — No `--subtitle` for docs.** Single-document publications don't have
the title/subtitle split a book cover does. Add later if a real document
needs one.

**D7 — Typst partial path: assume `../shared/typst-show.typ` works as-is.**
Courses use this same path and it resolves through the symlink. If the
phase 5 render fails because the doc project root resolves differently
than the book root, fall back to copying the course template's
`orange-book/` subdir convention. Decide based on the actual error.

---

## Phase 1 — Refactor scaffolder for reuse [ ]

**Files:** `material_core/cli.py`, `material_core/_scaffold.py`

- [ ] Drop the unused `PLACEHOLDERS` constant from `_scaffold.py` (it
      hard-codes course-only tokens and is never imported).
- [ ] Add private helper in `cli.py`:
      ```python
      def _scaffold_project(
          project_type: str,        # "course" | "doc"
          template_subdir: str,
          name: str,
          title: str | None,
          extra_placeholders: dict[str, str],
          next_steps: list[str],
      ) -> None
      ```
      Responsibilities: name regex check, manifest load, duplicate check,
      dest existence check, `copy_template`, `substitute_placeholders`,
      `add_project(..., type_=project_type)`, `save_manifest`, echo
      "created <type> <name>" + supplied `next_steps` lines.
- [ ] Add private helper in `cli.py`:
      ```python
      def _remove_project(label: str, name: str, yes: bool) -> None
      ```
      `label` is `"course"` or `"document"` for messages. Body is the
      current `course_remove` logic verbatim, parameterized.
- [ ] Rewrite `course_add` and `course_remove` as thin wrappers over the
      helpers. Verify by running existing manual flow:
      `matctl course add scratch-course && matctl course remove scratch-course --yes`
      against a throwaway clone of `material/`.

---

## Phase 2 — Doc template [ ]

**Files:** `material_core/templates/doc/_quarto.yml`,
`material_core/templates/doc/index.qmd`,
`material_core/templates/doc/assets/.gitkeep`

- [ ] `_quarto.yml`:
      ```yaml
      project:
        type: default
        output-dir: _output

      format:
        html:
          theme:
            - cosmo
            - ../shared/base.scss
          toc: true
          toc-depth: 3
          number-sections: true
          smooth-scroll: true
        orange-book-typst:
          output-file: {{DOC_NAME}}.pdf
          number-sections: true
          toc: true
          toc-depth: 2
          template-partials:
            - ../shared/typst-show.typ
      ```
- [ ] `index.qmd`:
      ```markdown
      ---
      title:  "{{DOC_TITLE}}"
      author: "Prof. Dr.-Ing. Peter Fröhlich"
      date:   today
      ---

      Document body — replace with content.
      ```
- [ ] `assets/.gitkeep` — empty file so the directory ships in the wheel.
- [ ] Confirm `pyproject.toml` package-data globs already pick up
      `templates/**/*` recursively (REQ-004 should have set this up; if
      not, extend to include `templates/doc/**`).

---

## Phase 3 — `matctl doc` CLI group [ ]

**File:** `material_core/cli.py`

- [ ] Add `@main.group() def doc()` — docstring "Manage standalone
      documents in a material checkout."
- [ ] `doc_add(name, title)` — calls `_scaffold_project("doc", "doc", ...)`
      with placeholders `{{DOC_NAME}}`, `{{DOC_TITLE}}` and next-steps:
      ```
      quarto preview <name>
      git add <name>/ projects.yml
      git commit -m 'Add doc: <name>'
      git push
      ```
- [ ] `doc_remove(name, yes)` — calls `_remove_project("document", name, yes)`.
- [ ] Help strings differentiate "course" vs "standalone document"
      everywhere they appear.

---

## Phase 4 — Manual verification with throwaway doc [ ]

- [ ] `pipx install --editable /home/peter/projects/material-core --force`.
- [ ] `cd /home/peter/material && matctl doc add demo-doc --title "Demo Doc"`.
- [ ] Verify: `demo-doc/_quarto.yml`, `demo-doc/index.qmd`,
      `demo-doc/assets/` exist; `projects.yml` has new entry with
      `type: doc`; placeholders are substituted.
- [ ] `quarto render demo-doc` → expect `demo-doc/_output/index.html` and
      `demo-doc/_output/demo-doc.pdf`. **If Typst partial path fails,
      revisit D7.**
- [ ] Open the HTML, sanity-check brand styling matches a course HTML.
- [ ] `matctl doc remove demo-doc --yes` → directory and manifest entry
      gone.
- [ ] Sanity: `matctl course add scratch && matctl course remove scratch
      --yes` still works (regression check for the helper refactor).

---

## Phase 5 — Migrate `esp-survival-guide` (acceptance vehicle) [ ]

The file is already at
`/home/peter/material/digital-und-mikrocomputertechnik/esp-survival-guide.qmd`,
moved out of `chapters/` in preparation. Promote it to a top-level doc:

- [ ] `cd /home/peter/material && matctl doc add esp-survival-guide --title "ESP32 Survival Guide"`.
- [ ] `mv digital-und-mikrocomputertechnik/esp-survival-guide.qmd esp-survival-guide/index.qmd`
      (overwrites the template `index.qmd`).
- [ ] Re-add the YAML front matter `author` / `date` lines from the
      template if the existing file omits them, so the rendered output has
      consistent metadata. (The current file has only `title:`.)
- [ ] `quarto render esp-survival-guide` → confirm clean HTML + PDF build
      with brand styling and no manual fixes beyond front matter.
- [ ] Verify `digital-und-mikrocomputertechnik/_quarto.yml` does not still
      reference `esp-survival-guide.qmd` in its chapter list (it
      shouldn't, since the file was already moved out — but check).

---

## Phase 6 — Documentation [ ]

- [ ] `docs/administration.md` — new "Project types: course vs. doc"
      section. Course = multi-chapter book + slides, deployed under
      `<name>/` with HTML in `_output/book/` and slides in
      `_output/slides/`. Doc = single-file publication, no slides, flat
      `_output/`. Cross-link to the lifecycle command sections.
- [ ] `docs/administration.md` — add `matctl doc add/remove` to the matctl
      command reference.
- [ ] `material/CLAUDE.md` — short note on when to choose `course` vs
      `doc`, and the `matctl doc add` command. (Edit happens in
      `material/`, separate commit.)
- [ ] `material-core/CLAUDE.md` — extend the matctl section to list the
      new commands. Update "Current status" line: REQ-005 DONE.

---

## Phase 7 — CI end-to-end (acceptance gate) [ ]

The matrix workflow's `doc` branch is currently dormant. REQ-005 is the
first requirement to fire it.

- [ ] Commit phase 5 to `material/`:
      `git add esp-survival-guide/ projects.yml && git rm digital-und-mikrocomputertechnik/esp-survival-guide.qmd 2>/dev/null` (file was moved into `esp-survival-guide/index.qmd`, so this should be a rename in git's eyes).
- [ ] Push to `main`. Watch the workflow:
  - [ ] `changes` job picks up `esp-survival-guide` as the changed
        project.
  - [ ] `build` job resolves `PROJECT_TYPE=doc`, takes the doc render
        branch (`quarto render esp-survival-guide` only, no slides).
  - [ ] Deploy step takes the doc deploy branch
        (`scp -r esp-survival-guide/_output/* …/esp-survival-guide/`).
- [ ] Verify `https://material.professorfroehlich.de/esp-survival-guide/`
      serves the rendered HTML and the PDF link works.

---

## Phase 8 — Release v0.4.0 [ ]

Roll the workflow pin bump (currently lagging at `v0.2.0`, behind released
`v0.3.0`) into the same release rather than splitting it.

- [ ] Bump `pyproject.toml` version → `0.4.0`. New CLI commands → minor.
- [ ] Commit, tag `v0.4.0`, push tag.
- [ ] In `material/.github/workflows/publish.yml`: bump
      `MATERIAL_CORE_REF` from `v0.2.0` to `v0.4.0` (skipping the dormant
      v0.3.0 pin since `matctl token` isn't used in CI). Commit.
- [ ] Re-trigger CI (manual dispatch or piggyback on the phase 7 push if
      ordering allows) to confirm the bumped pin still builds the doc
      project clean.
- [ ] Mark REQ-005 DONE in `docs/requirements/REQ-005.md` and
      `REQUIREMENTS_INDEX.md`. Set Completed date and Verified-by.

---

## Critical files

| File | Change |
|------|--------|
| `material_core/cli.py` | Add `doc` group, extract `_scaffold_project` and `_remove_project` helpers, refactor `course_add`/`course_remove` to use them |
| `material_core/_scaffold.py` | Drop unused `PLACEHOLDERS` constant |
| `material_core/templates/doc/_quarto.yml` | NEW — single-document project, HTML + Typst PDF |
| `material_core/templates/doc/index.qmd` | NEW — placeholder body |
| `material_core/templates/doc/assets/.gitkeep` | NEW |
| `pyproject.toml` | Version → 0.4.0; verify package-data picks up `templates/doc/**` |
| `docs/administration.md` | Course vs doc section + `matctl doc` command reference |
| `CLAUDE.md` (this repo) | matctl section + "Current status" line |
| `material/CLAUDE.md` | Course vs doc note (separate commit) |
| `material/.github/workflows/publish.yml` | `MATERIAL_CORE_REF: v0.4.0` (separate commit) |
| `material/projects.yml` + `material/esp-survival-guide/` | Migrated doc (separate commit) |
| `docs/requirements/REQ-005.md`, `REQUIREMENTS_INDEX.md` | Status DONE, completion date |

---

## Risks and trade-offs

- **Typst partial resolution (D7)** — only real unknown. Mitigation: phase
  4 catches it on the throwaway `demo-doc` before `esp-survival-guide`
  migration; fallback is the course template's `orange-book/` directory
  pattern.
- **Helper extraction regression** — refactoring `course add/remove` to
  share code with `doc add/remove` could subtly break the course path.
  Mitigation: phase 4 includes an explicit course-roundtrip regression
  check after the refactor.
- **Workflow pin skipping v0.3.0** — going `v0.2.0` → `v0.4.0` in one
  bump. Safe because v0.3.0 only added `matctl token`, which CI does not
  invoke. Document this in the workflow commit message.
- **Naming churn deferred** — shipping `doc` knowing it may later become
  `article` means a future breaking rename. Acceptable: REQ-005 needs to
  ship to unblock `esp-survival-guide`, and bundling a rename would double
  the scope and require coordinating a v1.0.0 break.
