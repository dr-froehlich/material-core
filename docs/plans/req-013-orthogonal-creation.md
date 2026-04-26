# REQ-013 Implementation Plan — Orthogonal universal document creation

**Goal:** Replace the two frozen scaffold commands (`course add`, `doc add`)
with a single universal creation flow whose three orthogonal axes —
**structure** (single-file vs multi-chapter), **slides** (with vs without),
and **brand** (which visual brand to apply) — can be combined freely. All
eight combinations must scaffold cleanly, render under `quarto render`, and
round-trip through `projects.yml` so downstream consumers (landing page
generator, CI matrix, future commands) can reconstruct the three choices
from the manifest alone.

**Context:** Today's templates encode two specific combinations:

| Command       | Structure        | Slides | Brand |
|---------------|------------------|--------|-------|
| `course add`  | multi-chapter    | yes    | thd   |
| `doc  add`    | single-file      | no     | thd   |

The schutzkonzept project surfaced a real combination the system can't
express: multi-chapter, no slides, non-THD brand. REQ-013 generalises the
creation surface; REQ-014 (hard dependency) supplies the brand registry
that `--brand` selects from. REQ-012 (already DONE) is inherited by every
multi-chapter variant via the chapter/index template fragments.

**Scope boundary:** This requirement covers (a) the universal creation
command and its supporting template-composition machinery, (b) the
manifest schema that records the three axes, (c) the `modify` surface
update for the new fields, (d) thin compatibility for `course add` /
`doc add`, and (e) doc updates. It does *not* introduce new brands
(REQ-014) and does *not* change the Worker, deploy paths, group landing
pages beyond brand awareness, token CLI, or Quarto rendering options
beyond what each scaffolded variant minimally needs.

**Status tracking:** `[ ]` open · `[~]` in progress · `[x]` done

---

## Design decisions

### D1 — Command name: `matctl project add` (and siblings)

The new universal verb lives under a new top-level group `project`:

```
matctl project add    <name> [orthogonal flags] [common flags]
matctl project remove <name> [--yes]
matctl project modify <name> [--title …] [--group …] [--brand …]
```

Rationale:

- `course` and `doc` are *combinations*, not categories — keeping them
  as top-level verbs alongside `project` would re-cement the old framing.
- `project` is the noun already used in `projects.yml` and the manifest
  helpers (`add_project`, `remove_project`, `_scaffold_project`,
  `_modify_project`), so the implementation maps naturally.
- The `group` verb stays distinct: groups are not projects in the
  scaffold sense (no on-disk content tree, no brand, no slides).

### D2 — `course add` / `doc add`: removed outright in this requirement

Per REQ-013 acceptance criterion 4 ("become thin shortcuts **or** are
deprecated with a migration note"), this plan picks **clean removal**:

- `matctl course add/remove/modify` and `matctl doc add/remove/modify`
  are deleted in the same release that introduces `matctl project …`.
- The `course` and `doc` click groups are removed from `cli.py`. Top
  hits (`matctl course add`) fall through to click's default
  unknown-command error, which lists the available groups including
  `project`.
- Migration note in the changelog v0.7.0 spells out the one-to-one
  replacement:

  ```
  matctl course add  → matctl project add --structure chapters --slides     --brand thd
  matctl doc    add  → matctl project add --structure single   --no-slides  --brand thd
  matctl course remove / doc remove → matctl project remove
  matctl course modify / doc modify → matctl project modify
  ```

Decision documented here per REQ-013 acceptance criterion 4.

Rationale for the clean cut over a shim release:

- The user is the only operator; muscle memory is a one-day adjustment,
  not a fleet-wide migration.
- Carrying shims means freezing two flag surfaces (D8 below) for a
  release window — extra surface, extra confusion when `--brand` works
  on `project modify` but not `course modify`.
- Deleting the old templates and old click handlers in the same commit
  collapses the entire surface in one reviewable change.

Consequence: `material/projects.yml` legacy entries (`type: course` /
`type: doc`) still need to be migrated — that's the in-memory + on-save
normalisation in D10. Reading is permissive; writing is always in the
new schema.

### D3 — `projects.yml` schema: three explicit axis fields, no enum

Each project entry gains three explicit fields:

```yaml
- name:       schutzkonzept
  type:       project        # was: course | doc
  title:      "Schutzkonzept"
  group:      pfarrei
  structure:  chapters       # chapters | single
  slides:     false          # bool
  brand:      generic        # any registered brand id (REQ-014)
  lang:       de
```

Rationale:

- **Three explicit booleans/enums** beat a single `type` enum of eight
  values: a downstream consumer that only cares about brand (e.g. landing
  page styling) reads one field, not a parsed compound.
- `structure: chapters | single` rather than `chapters: bool` — the field
  reads cleanly out loud and leaves room for a future `structure: slides`
  (slides-only project, no prose) without a schema migration.
- `slides: bool` — the simplest boolean axis; no other values are
  meaningful.
- `brand:` — a string id that must resolve in the brand registry; defined
  by REQ-014, validated at scaffold/modify time.
- `lang:` already lives in templates as `{{LANG}}` (REQ-010); promote it
  to a manifest field too so the landing page can pick it up (see D9).
  Existing entries with no `lang:` field default to `de` for backwards
  compatibility — matches today's de-only fleet.
- `type:` collapses to a single value `project` for the new universal
  flow. Existing `type: course` / `type: doc` / `type: group` entries are
  migrated in-place at first manifest load (see D11). `type: group` is
  unchanged — groups are not projects.

### D4 — Template layout: fragment composition, not eight templates

Eight templates would mean eight copies of `_quarto.yml`, two copies of
`orange-book/`, four copies of every common fragment. Fragment
composition keeps maintenance tractable and matches the orthogonal
model. Layout:

```
material_core/templates/
  _base/                       — shared by every project
    orange-book/               — typst includes (currently duplicated)
    assets/.gitkeep
  structure/
    chapters/                  — chapters/, _shared/, index.qmd (book preface), _quarto.book.fragment.yml
      chapters/01-introduction.qmd
      _shared/_exercise-example.qmd
      index.qmd                — `{.unnumbered}` preface (REQ-012)
      _quarto.fragment.yml     — book-specific keys: project.type=book, book: {…}, output-dir
    single/                    — single index.qmd, no chapters/, no _shared/
      index.qmd
      _quarto.fragment.yml     — single-doc keys: project.type=default, output-dir
  slides/                      — only copied when --slides
    slides/01-introduction.qmd
    slides/_quarto.yml
  _quarto.common.fragment.yml  — keys shared by both structures: lang, format.html.theme, format.orange-book-typst.template-partials, etc.
```

The scaffolder composes the destination by:

1. Copying `_base/` into `dest/`.
2. Copying the chosen `structure/<structure>/` overlay (everything
   *except* its `_quarto.fragment.yml`) into `dest/`.
3. If `slides=True`, copying `slides/` into `dest/slides/`.
4. Composing `dest/_quarto.yml` by merging
   `_quarto.common.fragment.yml` + the structure's
   `_quarto.fragment.yml` + a slides-specific block (only when
   `slides=True` — adds the slides project to the book listing or, for
   single-file, just leaves a `slides:` subdirectory rendered separately
   by Quarto via its own `_quarto.yml`).
5. Merging `brand_placeholders(brand)` into the substitution dict.
   **No per-brand `_quarto.fragment.yml` exists** — REQ-014 settled
   brand's Quarto-level keys via placeholder substitution instead.
   The two tokens `{{LOGO_LINE}}` and `{{FAVICON_LINE}}` live in the
   structure fragments' assembled `_quarto.yml` and are resolved in
   step 6.
6. Running `substitute_placeholders(dest, placeholders)` over the
   assembled tree (placeholders include both project-level and brand
   tokens).

Merge semantics: load each fragment with `ruamel.yaml`, merge with a
deep-merge function that prefers the later fragment for scalar conflicts
and concatenates lists (needed for `book.chapters`). Implemented in a
new `material_core/_compose.py`. Pure function, unit-testable.

### D5 — Slides composition detail

`structure=chapters, slides=True` → today's `course` layout exactly:
`book.chapters: [index.qmd, chapters/01-introduction.qmd]` plus a
sibling `slides/` rendered as its own Quarto project. The book's
`_quarto.yml` does *not* list slides; `slides/_quarto.yml` is
self-contained today. Keep that structure.

`structure=single, slides=True` → single `index.qmd` plus sibling
`slides/` directory. The two render independently. CI's per-project
build step already invokes `quarto render <project-dir>`, which renders
both because `slides/` has its own `_quarto.yml`. (Verify in Phase 6.)

`*, slides=False` → no `slides/` directory copied at all. Acceptance
criterion 6 explicitly forbids leaving an empty `slides/` behind — the
overlay copy is conditional, not a copy-then-delete.

### D6 — Brand application (updated against actual REQ-014 surface)

Brand application is deliberately thin in REQ-013:

- `--brand <id>` is validated with `brand in available_brands(_package_root())`
  (`material_core._projects.available_brands`). No separate `is_registered()`.
- Scaffolder writes the brand id into the manifest entry (`brand:` field).
- At scaffold time, `brand_placeholders(brand)` (`material_core._brand_resolve`)
  is merged into the substitution dict passed to `substitute_placeholders` — this
  resolves `{{LOGO_LINE}}` and `{{FAVICON_LINE}}` in the assembled `_quarto.yml`.
  **There is no per-brand `_quarto.fragment.yml`** — D4 step 5 is therefore
  replaced by a substitution-dict merge, not a YAML deep-merge step.
- Symlinks: `link_project(project_dir, brand, pkg_root)` from
  `material_core._brand_resolve` wires the three per-project symlinks; REQ-013
  calls this after `compose()` exactly as REQ-014's `_scaffold_project` does.
- `modify --brand`: REQ-014's `relink_project` only rewires symlinks. The
  baked `_quarto.yml` (favicon path, sidebar.logo path) is **not** updated by
  REQ-014. REQ-013's `project modify --brand` must also rewrite these keys in
  place — using `ruamel.yaml` to load `_quarto.yml`, update `book.favicon` and
  `book.sidebar.logo` (setting them to the new brand's asset paths, or removing
  them for `generic`). This is the one place REQ-013 adds logic on top of
  REQ-014. See Phase 4.5.
- Backwards compatibility: `resolve_brand(entry)` returns `"thd"` for legacy
  entries with no `brand:` key (REQ-014 acceptance criterion 7). No change here.

REQ-014 is DONE; REQ-013 plugs into the registry without reinventing brand machinery.

### D7 — `project modify`: which transitions are safe

Per REQ-013 acceptance criterion 5, `modify` accepts axis flags but
must reject physically meaningless transitions:

| Field        | Modifiable after content exists?                     | Mechanism                                                         |
|--------------|------------------------------------------------------|-------------------------------------------------------------------|
| `--title`    | yes                                                  | write-through to `_quarto.yml:book.title` or `index.qmd` frontmatter |
| `--group`    | yes                                                  | manifest only (deploy path changes; remote cleanup manual, as today) |
| `--brand`    | yes                                                  | manifest update + `matctl link` re-resolves on next invocation; brand-specific `_quarto.yml` keys get rewritten in place |
| `--slides`   | only `false → true` (additive); `true → false` rejected when `slides/` exists with content | additive: copy slides overlay into existing project; destructive: refuse |
| `--structure`| **rejected outright** — `chapters ↔ single` requires content reorganisation matctl can't safely automate | clear error message with manual-migration hint |
| `--lang`     | yes (template-only knob — affects crossref labels)   | manifest update + rewrite of the `lang:` line in `_quarto.yml` / front matter |

Rejected transitions raise a `ClickException` with one-line guidance
("structure flip not supported automatically; create a new project and
move content by hand"). No half-state on disk: validation happens before
any mutation.

`--slides true → false` when `slides/` has only the scaffolded skeleton
(detection: directory mtime equals creation, no files outside the
template's manifest of slide files) is **not** auto-removed in v1 —
keep behaviour conservative: refuse, explain. Reconsider if needed.

### D8 — `project modify` is the only modify surface

With D2 removing `course modify` / `doc modify` outright, `project
modify` is the sole entry point for any field change (`--title`,
`--group`, `--brand`, `--slides`, `--lang`, and the always-rejecting
`--structure`). No flag-surface duplication to reason about.

### D9 — Group landing pages: brand-neutral, language-aware

REQ-009 landing pages currently hard-code `lang="en"` and use no
branding. With REQ-013 + REQ-014:

- **Brand:** landing pages are brand-neutral — **settled in REQ-014 D5**.
  Groups carry no `brand:` field; the landing page does not read child
  `brand:` fields. No change here.
- **Language:** if every child shares the same `lang:` value, render the
  landing page in that language (`<html lang="…">` + a localised "Courses"
  / "Documents" heading). If children mix languages, fall back to `en`
  and a neutral heading set ("Materials"). Implementation: a small
  `_landing._pick_lang(children) -> str | None` helper.
- The "Courses" / "Documents" split currently keys on `type ==
  "course"` / `type == "doc"`. With the new `type: project` + `structure:
  chapters/single` schema, the rule becomes: `structure == "chapters"`
  → "Courses"; `structure == "single"` → "Documents". Naming is
  deliberately preserved for user familiarity even though "Course" is no
  longer literally what's recorded.

### D10 — Backwards compatibility: in-place manifest migration on load

`load_manifest` gains a normalisation pass that mutates legacy entries
into the new shape *in memory* on every load:

- `type: course` → `type: project, structure: chapters, slides: True,
  brand: thd` (and write `lang: de` if absent).
- `type: doc` → `type: project, structure: single, slides: False,
  brand: thd` (and write `lang: de` if absent).
- `type: group` → unchanged.

Crucially, **the migration is also persisted** the next time
`save_manifest` is called for any other reason (a `project modify`, a
`project add`). The migration is not a separate "v0.6.0 upgrade" command
because (a) the manifest is small and hand-readable, (b) `ruamel.yaml`
preserves comments and ordering, (c) drifting between in-memory and
on-disk shapes for an extended period invites bugs. A dedicated
`matctl manifest migrate` command is **not** added — too heavyweight for
the scale of change.

A one-paragraph note in the changelog announces the manifest schema
bump; the format is fully forward-compatible (extra fields on entries),
so a v0.5.x matctl reading a v0.6.0 manifest will simply ignore the new
fields and treat everything as `course`/`doc` — that's a regression for
the consumer's *behaviour* (wrong template assumptions) but not a parse
failure. Tagging strategy: bump to **v0.6.0** because the CLI surface
changes (new top-level verb, deprecated old verbs).

### D11 — Eight smoke tests as the verification contract

No automated test suite (matches the rest of matctl). Phase 7 lists
eight manual smoke runs — one per combination — that each scaffold a
project into a throwaway checkout and run `quarto render` to confirm
the output. The eight runs *are* the acceptance criterion.

### D12 — Out of scope for REQ-013

- New brands beyond what REQ-014 ships (brand additions are REQ-014's
  job; REQ-013 just consumes the registry).
- Slides-only projects (`structure: slides`, no prose). Reserved for a
  future requirement; the schema in D3 leaves room.
- `--structure` flip migration tooling.
- A `matctl project list` command. Could be added later; not required
  by REQ-013.
- Any change to the Worker, token CLI, or CI deploy structure beyond
  what naturally follows from a new manifest schema (the CI matrix job
  enumerates `type: project` instead of `type in (course, doc)` —
  trivial yaml/jq tweak).

---

## Phase 0 — Pre-flight: confirm REQ-014 is in place

- [x] **0.1** REQ-014 has shipped — `v0.6.0`, committed `704eba4`.
- [x] **0.2** REQ-014's brand-registry public surface (confirmed, differs
      from what this plan assumed — D6 and Phase 2 are updated accordingly):

      | Assumed here              | Actual REQ-014 surface                          |
      |---------------------------|-------------------------------------------------|
      | `brands.list_ids()`       | `_projects.available_brands(pkg_root: Path) -> list[str]` |
      | `brands.is_registered(id)`| `brand in available_brands(pkg_root)`           |
      | `brands.fragment_path(id)`| **does not exist** — see Point 2 below          |

      REQ-014 ships **no per-brand `_quarto.fragment.yml`**. Brand contributes
      Quarto-level keys (favicon, sidebar.logo) via placeholder substitution
      only: `_brand_resolve.brand_placeholders(brand) -> dict[str, str]`
      returns `{"{{LOGO_LINE}}": ..., "{{FAVICON_LINE}}": ...}`. D4 step 5
      and Phase 2.4 step 4 are updated to match.

## Phase 1 — Template restructure (`material_core/templates/`)

All edits in `material_core/templates/`. Deliberate, reviewable in
isolation; no behaviour change yet (cli.py still points at `course/`
and `doc/`).

- [x] **1.1** Create `_base/` with `orange-book/` (copied from
      `course/orange-book/` — the doc copy is byte-identical;
      verify with `diff -r`) and `assets/.gitkeep`.
- [x] **1.2** Create `structure/chapters/` containing
      `chapters/01-introduction.qmd`, `_shared/_exercise-example.qmd`,
      `index.qmd` (the REQ-012 unnumbered preface), and a
      `_quarto.fragment.yml` carrying only the keys that differ
      between book and single-file projects:
      ```yaml
      project:
        type: book
        output-dir: _output/book
      book:
        title:    "{{PROJECT_TITLE}}"
        subtitle: "{{PROJECT_SUBTITLE}}"
        author:   "Prof. Dr.-Ing. Peter Fröhlich"
        date:     today
        favicon:  THD-logo.png   # overridden by brand fragment
        sidebar:
          logo:   THD-logo.png   # overridden by brand fragment
        chapters:
          - index.qmd
          - chapters/01-introduction.qmd
      ```
- [x] **1.3** Create `structure/single/` containing `index.qmd` (from
      today's `doc/index.qmd`) and a `_quarto.fragment.yml`:
      ```yaml
      project:
        type: default
        output-dir: _output
      ```
      Plus the front-matter title interpolation that today's `doc`
      template carries.
- [x] **1.4** Create `slides/` overlay containing
      `slides/01-introduction.qmd` and `slides/_quarto.yml`, copied
      verbatim from `course/slides/`.
- [x] **1.5** Create `_quarto.common.fragment.yml` with everything
      both structures share: top-level `lang: {{LANG}}`,
      `format.html.{theme,toc,toc-depth,number-sections,…}`,
      `format.orange-book-typst.{output-file: {{PROJECT_NAME}}.pdf,
      number-sections, toc, toc-depth, template-partials}`. Only
      include keys that are identical today between course's and
      doc's `_quarto.yml`.
- [x] **1.6** Rename placeholder tokens to be project-type-agnostic:
      `{{COURSE_NAME}}` / `{{DOC_NAME}}` → `{{PROJECT_NAME}}`,
      `{{COURSE_TITLE}}` / `{{DOC_TITLE}}` → `{{PROJECT_TITLE}}`,
      `{{COURSE_SUBTITLE}}` → `{{PROJECT_SUBTITLE}}`. `{{LANG}}`
      stays.
- [x] **1.7** Delete the old `material_core/templates/course/` and
      `material_core/templates/doc/` directories — D2 removes the
      verbs that referenced them, so leaving them behind is dead
      weight. Verify with `grep -r "templates/course\|templates/doc"
      material_core/` that nothing in the package still points at
      them.

## Phase 2 — Template composer (`material_core/_compose.py`, new module)

- [x] **2.1** Module skeleton: `compose(dest: Path, *, structure:
      str, slides: bool, brand: str, placeholders: dict[str, str]) ->
      None`. Pure orchestration; no `click` dependency.
- [x] **2.2** Implement `_deep_merge(a, b) -> CommentedMap` over
      `ruamel.yaml` types: scalar/dict/list rules per D4. Lists from
      `b` extend lists from `a` (book.chapters), scalars from `b`
      win, dicts merge recursively. Behaviour is a pure function;
      add docstring examples.
- [x] **2.3** Implement `_load_fragment(path: Path) -> CommentedMap`
      using the same ruamel config as `_projects.py`.
- [x] **2.4** Implement `compose`:
      1. `copy_template("_base", dest)` (reuse `_scaffold.copy_template`).
      2. Overlay-copy `structure/<structure>/` into `dest/`,
         skipping `_quarto.fragment.yml`.
      3. If `slides`, overlay-copy `slides/` into `dest/`.
      4. Build `_quarto.yml` by deep-merging:
         `common.fragment` + `structure/<structure>/_quarto.fragment.yml`
         — write the result to `dest/_quarto.yml`. **No brand fragment
         step** — brand knobs enter via substitution (step 5).
      5. Build the full substitution dict: project-level tokens
         (`{{PROJECT_NAME}}`, `{{PROJECT_TITLE}}`, `{{LANG}}`, …) plus
         `brand_placeholders(brand)` from `material_core._brand_resolve`
         (adds `{{LOGO_LINE}}` / `{{FAVICON_LINE}}`). Pass the merged
         dict to `substitute_placeholders(dest, …)`.
      6. Call `link_project(dest, brand, pkg_root)` to wire the three
         per-project brand symlinks (`_brand.yml`, `brand.scss`,
         `brand-assets/`).
- [x] **2.5** Add a `_overlay_copy(src: Path, dest: Path)` helper —
      `copytree` with `dirs_exist_ok=True` and a single-file skip
      list. `shutil.copytree(..., ignore=shutil.ignore_patterns("_quarto.fragment.yml"))`
      handles the skip cleanly.
- [x] **2.6** Defensive checks: unknown `structure` value, missing
      fragment file, unknown brand id (`brand not in
      available_brands(_package_root())` — uses
      `material_core._projects.available_brands`, not a separate
      `is_registered` function). Each raises a typed exception that
      the cli layer maps to `ClickException`.

## Phase 3 — Manifest schema (`material_core/_projects.py`)

- [x] **3.1** Extend `add_project` signature to accept `structure: str,
      slides: bool, brand: str, lang: str` and write them into the
      entry. Keep field write order stable (`name, type, title, group,
      structure, slides, brand, lang`) for readable diffs.
- [x] **3.2** Add `_normalise_legacy(doc: CommentedMap) -> bool` —
      walk `doc["projects"]`, rewrite `type: course` and `type: doc`
      entries per D10. Return `True` if any entry was rewritten so
      callers can decide whether to persist. Default `lang: de` when
      absent.
- [x] **3.3** Call `_normalise_legacy` from `load_manifest` so every
      consumer sees the new shape. The function rewrites the
      `CommentedMap` in place; persistence happens whenever the next
      `save_manifest` runs (D10). Add a one-line `click.echo` (via a
      callback param so the function stays click-free, OR just leave
      logging silent and document the schema bump in the changelog —
      **prefer silent**: a noisy migration on every read is worse than
      a quiet one-time write). The schema is forward-readable, so the
      silent path is safe.
- [x] **3.4** Add `update_axes(entry: CommentedMap, *, structure:
      str | None, slides: bool | None, brand: str | None, lang: str |
      None) -> list[str]` returning a list of human-readable change
      descriptions for `click.echo`. Used by `project modify`.

## Phase 4 — CLI: `project` verb (`material_core/cli.py`)

- [x] **4.1** Add a new `@main.group("project")` with `add`, `remove`,
      `modify` subcommands. Place it above the deprecated `course`
      and `doc` groups in source order so it reads as the primary
      surface.
- [x] **4.2** `project add` flag surface:
      ```
      --structure [chapters|single]   required
      --slides / --no-slides          required (no default — force user choice)
      --brand <id>                    required (validated against REQ-014 registry)
      --lang [de|en]                  required (today's REQ-010 contract)
      --title TEXT                    optional (default: title-cased slug)
      --subtitle TEXT                 optional (only used when structure=chapters)
      --group TEXT                    optional
      ```
      Refuse the run if `--subtitle` is passed with `--structure single`
      (single-file index.qmd has no subtitle slot).
- [x] **4.3** Refactor `_scaffold_project` to drive the new composer:
      thread `structure`, `slides`, `brand`, `lang` through to
      `compose()` and `add_project()`. The dest-existence and group-
      existence checks stay where they are.
- [x] **4.4** `project remove` — body is essentially today's
      `_remove_project`, no changes needed beyond renaming the click
      command.
- [x] **4.5** `project modify` flag surface adds `--brand`, `--slides
      / --no-slides`, `--lang`, `--structure` (the last only to fail
      loudly per D7). Implement the transition matrix in D7.

      For `--brand`: REQ-014's `relink_project` only rewires the three
      per-project symlinks; it does **not** update the baked favicon /
      sidebar.logo paths in `_quarto.yml`. REQ-013 must do this targeted
      YAML rewrite here. Approach: use `ruamel.yaml` to load
      `_quarto.yml`, update (or delete for `generic`) `book.favicon`
      and `book.sidebar.logo`, write back. The key set is small and
      bounded. Order of operations: manifest update → `relink_project`
      → `_quarto.yml` YAML rewrite.

      For `--lang`: edit the top-level `lang:` line in `_quarto.yml`
      (chapters) or front matter (single).
- [x] **4.6** Centralise affected-group regeneration: every mutating
      handler ends with `_regenerate_affected_groups(...)` exactly
      like today (REQ-009 D2). Brand changes affect *no* group's
      landing page (D9 — landing pages are brand-neutral) but lang
      changes *may* (D9 — landing-page lang derives from children).
      The simplest rule: regenerate the entry's group on every modify
      regardless of which axis changed.

## Phase 5 — Remove `course` and `doc` click groups

- [x] **5.1** Delete the `@main.group()` definitions for `course` and
      `doc` and all their subcommands (`course_add`, `course_remove`,
      `course_modify`, `doc_add`, `doc_remove`, `doc_modify`) from
      `cli.py`.
- [x] **5.2** Remove now-unused imports (`title_case_from_slug` may
      stay — `project add` still needs it).
- [x] **5.3** Spot-check: `grep -nE "\\bcourse\\b|\\bdoc\\b" cli.py`
      should only show occurrences inside docstrings, the
      deprecation note in the changelog reference, or the legacy-
      manifest migration code in `_projects.py`.
- [x] **5.4** Leave `_scaffold_project`, `_remove_project`,
      `_modify_project`, `_rewrite_title` in place — `project add/
      remove/modify` reuse them. Trim parameters that only existed
      to distinguish course vs doc (e.g. the `label` parameter
      driving `_rewrite_title`'s branch can become `structure`-driven
      instead).

## Phase 6 — CI matrix update (`material/.github/workflows/publish.yml`)

The current build matrix enumerates entries with `type in (course,
doc)`. After D10's migration runs once and `projects.yml` is
re-saved, every former course/doc becomes `type: project`.

- [x] **6.1** Update the matrix-extraction `yq` expression in
      `material/.github/workflows/publish.yml`:
      ```
      yq '.projects[] | select(.type == "project") | .name' projects.yml
      ```
      (or for the transition window: `select(.type == "project" or
      .type == "course" or .type == "doc")`).
- [x] **6.2** Verify deploy paths (`<group>/<name>/` vs `<name>/`)
      are unchanged — the path derivation already keys on the
      `group:` field, not on `type`. Confirm by inspecting the build
      step source.
- [x] **6.3** REQ-009 landing job: `select(.type == "group")`
      already correct, no change.

## Phase 7 — Manual acceptance: eight scaffolds × `quarto render`

Run each in a throwaway checkout (`projects.yml` containing only an
empty `projects: []`, `matctl link` already run, REQ-014's brands
registered).

- [x] **7.1** `--chapters --slides     --brand thd     --lang de` →
      identical to today's `course add` output. `quarto render`
      succeeds. THD branding visible.
- [x] **7.2** `--chapters --slides     --brand generic --lang de` →
      same structure, no THD logo, generic favicon, generic primary
      colour.
- [x] **7.3** `--chapters --no-slides  --brand thd     --lang de` →
      no `slides/` directory present; `quarto render` succeeds; book
      sidebar lacks the slides cross-link (none was scaffolded
      anyway).
- [x] **7.4** `--chapters --no-slides  --brand generic --lang de` →
      **the schutzkonzept combination.** Verify it renders a
      multi-chapter book with no THD assets.
- [x] **7.5** `--single   --slides     --brand thd     --lang de` →
      single `index.qmd` plus sibling `slides/` rendered as a
      separate Quarto project. Both outputs land under `_output/`.
- [x] **7.6** `--single   --slides     --brand generic --lang de` →
      same as 7.5 with neutral brand.
- [x] **7.7** `--single   --no-slides  --brand thd     --lang de` →
      identical to today's `doc add` output.
- [x] **7.8** `--single   --no-slides  --brand generic --lang en` →
      single English doc, neutral brand. Verify English crossref
      labels.
- [x] **7.9** Inspect the resulting `projects.yml`: each of the
      eight entries carries `structure`, `slides`, `brand`, `lang`
      with the values used.
- [x] **7.10** `matctl project modify <name> --brand thd` on the
      generic-branded entry from 7.4: manifest updates,
      `_quarto.yml` favicon/sidebar.logo lines update, `matctl link`
      re-resolves, `quarto render` shows THD branding.
- [x] **7.11** `matctl project modify <name> --slides` on a
      `--no-slides` entry: `slides/` overlay is added, manifest
      reflects `slides: true`, `quarto render` builds both outputs.
- [x] **7.12** `matctl project modify <name> --structure single`
      on a chapters entry: rejected with the documented error
      message; on-disk state untouched.
- [x] **7.13** Legacy migration smoke: take a copy of the *current*
      `material/projects.yml` (with `type: course` / `type: doc`
      entries), run any `matctl project modify` no-op on one entry,
      then `git diff projects.yml` — every former course/doc entry
      should have grown `structure`, `slides`, `brand: thd`, `lang:
      de` fields.

## Phase 8 — Documentation

- [x] **8.1** `docs/authoring.md` — add a section "Choosing a project
      shape" with the 2×2×2 decision matrix and a one-line
      recommendation per cell. Cross-reference `--brand` to REQ-014's
      brand list.
- [x] **8.2** `docs/administration.md` — under the matctl reference,
      add `project add/remove/modify` documentation. Mark
      `course add` / `doc add` as deprecated shims with their frozen
      axis values.
- [x] **8.3** `CLAUDE.md` — replace the `course add` and `doc add`
      bullet lists with a single `project add` description that
      lists the orthogonal flags and shows the eight combinations
      in a compact table. Note the deprecation of the old verbs.
      Update "Current status" to add REQ-013 DONE on release.
- [x] **8.4** Changelog entry for v0.7.0 covering: the new `project`
      verb, the manifest schema bump (and that it auto-migrates),
      the removal of `course`/`doc` commands (REQ-014 v0.6.0 added
      `--brand` to them; REQ-013 v0.7.0 removes the commands outright),
      the eight supported combinations.

## Phase 9 — Release and close-out (`v0.7.0`)

Note: REQ-014 already shipped as `v0.6.0`. REQ-013 is `v0.7.0`.

- [x] **9.1** `material-core`: bump `pyproject.toml` to `0.7.0`.
- [x] **9.2** Tag `v0.7.0`, push.
- [x] **9.3** `material/.github/workflows/publish.yml`: update the
      pinned `material-core` version to `v0.7.0`.
- [x] **9.4** First `matctl project modify` no-op on any existing
      entry in `material/` to trigger the manifest re-save (D10) —
      commit the resulting `projects.yml` schema migration in one
      tidy commit.
- [x] **9.5** Tick all REQ-013 acceptance criteria, set Status DONE,
      Completed date, Verified by ("manual acceptance run 2026-…
      eight combinations + render").
- [x] **9.6** Update `REQUIREMENTS_INDEX.md`.

---

## Risks and mitigations

- **REQ-014 surface drift.** ~~REQ-013 plugs into a registry API not yet
  fully designed.~~ **Resolved by Phase 0.2.** The actual surface is
  `available_brands(pkg_root)` + `brand_placeholders(brand)`. No
  per-brand `_quarto.fragment.yml`. Consumer code (Phase 2.6, Phase 4.2,
  Phase 4.5) is updated to match.
- **Composer merge subtleties.** Deep-merging YAML with comment
  preservation is fiddly. Mitigation: keep fragments minimal — only
  keys that genuinely differ live in non-common fragments. The
  composer is a pure function and easy to eyeball-test against the
  eight Phase 7 outputs.
- **In-place schema migration on read.** A read-only consumer
  (someone running `matctl token list` from a worktree they don't
  intend to commit) could see drift between in-memory and on-disk
  shapes. Mitigation: the migration is idempotent and silent; the
  only visible effect is at the next `save_manifest`. Tolerable.
- **Existing local muscle memory.** The user has typed `matctl course
  add` for months and `matctl course add foo` will now error out.
  Mitigation: changelog v0.6.0 spells out the one-line replacements
  (D2); the click error already lists `project` as an available
  group. One-day adjustment for a single operator.
- **`--slides true → false` data loss.** If we later relax D7 to allow
  destructive removal, untracked slide content could be lost.
  Mitigation: keep refusing in v1 (D7); revisit only with a
  `--force` flag and an explicit warning.
- **CI matrix transition window.** While `material/projects.yml`
  carries a mix of `type: course` / `type: doc` / `type: project`
  during the migration commit, the matrix expression must accept
  both. Phase 6.1 covers this; the window collapses to one commit.

## Explicitly out of scope

- New brands (REQ-014).
- A slides-only structure variant (future requirement; schema leaves
  room — D3).
- Auto-migration tooling for `--structure` flips (D7).
- A `matctl project list` command.
- Worker / token / deploy-pipeline changes.
- Per-brand templates beyond the visual shim REQ-014 supplies (REQ-014
  acceptance criterion: brand scope is *strictly visual*).

## Commit strategy

`material-core`:

1. **Phase 1** — template restructure. Pure file moves + new
   fragments; no behaviour change because cli.py still points at the
   old `course/` and `doc/` directories. Reviewable in isolation.
2. **Phase 2** — `_compose.py`. New module, no callers yet.
3. **Phases 3 + 4 + 5** — manifest schema + new `project` verb +
   removal of `course`/`doc` groups in one commit. Atomic so the
   release never ships in a half-state where the old verbs are
   broken but the new one isn't yet wired.
4. **Phase 8** — documentation.
5. **Phase 9** — version bump + tag.

`material`:

- One commit covering Phase 6 (`publish.yml` matrix update) +
  Phase 9.4 (manifest schema migration).
