# REQ-014 Implementation Plan — Visual brand registry

**Goal:** Introduce a brand registry inside `material-core` so that projects
can opt into a non-THD visual identity at scaffold time. Ship three brands —
`generic` (default, brand-neutral, no logo, but using the THD colour palette),
`thd` (current behaviour, lecture material), and `pf` (Peter Fröhlich's
personal branding, using the warm-gold / light-warm palette behind
`logo_pf.svg`). Brand scope is **strictly visual**: logo, primary colour,
favicon, footer. Anything beyond the visual surface stays brand-neutral and
shared.

**Context:** Today THD is hard-coded throughout: `material_core/_brand.yml`
declares only `thd-*` palette entries; `shared/base.scss` references
`$thd-blue` directly; the course/doc templates reference `THD-logo.png` for
favicon and sidebar logo. The `material/` schutzkonzept project (a parish
document) made the THD assumption visible — there is no clean opt-out today.
REQ-008 made groups first-class with a `modify` seam (REQ-009 plan §D2);
REQ-014 reuses the same seam for a future `--brand` switch.

**Scope boundary:** Brand = visual surface only. The four assets per brand
are **logo** (PNG raster + optionally SVG), **favicon**, **primary colour**
(via `_brand.yml` palette), **footer text**. No author identity, no per-brand
language, no per-brand templates, no per-brand build flags, no per-brand
Worker/domain coupling (input §5 deferred). Brand-neutral assets — fonts,
theorems, mermaid defaults, base SCSS structure — stay in
`material_core/shared/` with a documented invariant that nothing
brand-specific lives there.

**Status tracking:** `[ ]` open · `[~]` in progress · `[x]` done

---

## Design decisions

### D1 — Three brands ship in v1

| Brand | Default? | Logo | Primary colour | Use case |
|---|---|---|---|---|
| `generic` | **yes** (new scaffolds) | none | THD blue (`#1a4273`) | Default for non-THD documents (e.g. schutzkonzept) — austere, no organisational marking |
| `thd` | implicit fallback for **legacy entries without `brand:` field** | `THD-logo.png` | THD blue (`#1a4273`) | Lecture material under THD |
| `pf` | opt-in | `logo_pf.svg` (copied from `pfhome/public/`) | warm-gold (`#d99d44`) with light-warm (`#e1c3a0`) accent | Peter Fröhlich's personal documents |

Two distinct defaults are deliberate (not a contradiction with REQ-014's
backwards-compatibility clause):

- **Scaffold default = `generic`.** `matctl course add` / `doc add` write
  `brand: generic` into the manifest unless `--brand` is passed. Future
  documents are non-THD by default.
- **Resolution default = `thd`.** When `_resolve_brand(entry)` is asked
  about an entry whose dict has no `brand:` key (existing pre-REQ-014
  manifest), it returns `thd`. That preserves the REQ-014 acceptance
  criterion "Existing projects without a `brand:` field continue to render
  identically to today (implicit `thd`)."

The two defaults never disagree: by the time `_resolve_brand` runs on a
freshly scaffolded entry, `brand:` is already populated.

### D2 — Brand assets live in `material_core/brands/<brand>/`

```
material_core/
  brands/
    generic/
      _brand.yml               — palette + footer; no logo block
      brand.scss               — brand-specific SCSS rules (colour application)
      assets/                  — empty (no logo, no favicon — see D6)
    thd/
      _brand.yml
      brand.scss
      assets/
        THD-logo.png           — moved from shared/assets/
        favicon.png            — symlink or copy of THD-logo.png
    pf/
      _brand.yml
      brand.scss
      assets/
        logo_pf.svg            — copied from /home/peter/projects/pfhome/public/
        favicon.svg            — same file (browsers accept SVG favicons)
  shared/
    base.scss                  — brand-neutral structure; uses Quarto brand SCSS vars
    typst-show.typ
    colors.tex
    assets/
      fonts/                   — stays here (brand-neutral)
      (THD-logo.png removed → moved to brands/thd/assets/)
```

Acceptance criterion "brand-neutral assets live outside `brands/`" is
enforced by inspection: a one-line note in `docs/administration.md` and a
review-time check. No automated lint in v1.

### D3 — `_brand.yml` per brand carries palette + logo + footer; SCSS overlay applies them

Each `brands/<brand>/_brand.yml` declares its own `color.palette`, `logo`
(or omits it), `typography` (shared subset — fonts come from `shared/`),
and a `meta.footer` string consumed by the SCSS overlay. The overlay
`brands/<brand>/brand.scss` is a tiny file that aliases the brand's
primary/secondary palette entries to the **brand-neutral** SCSS variable
names that `shared/base.scss` consumes:

```scss
// brands/thd/brand.scss
/*-- scss:defaults --*/
$brand-primary:   #1a4273;
$brand-secondary: #e8f0f7;
$brand-accent:    #e87722;
$brand-footer-text: "© THD — Technische Hochschule Deggendorf";
```

```scss
// brands/pf/brand.scss
/*-- scss:defaults --*/
$brand-primary:   #d99d44;  // warm-gold
$brand-secondary: #e1c3a0;  // light-warm
$brand-accent:    #164257;  // dark-accent (from pfhome tailwind config)
$brand-footer-text: "© Peter Fröhlich";
```

```scss
// brands/generic/brand.scss
/*-- scss:defaults --*/
$brand-primary:   #1a4273;  // THD blue, per requirement
$brand-secondary: #e8f0f7;
$brand-accent:    #e87722;
$brand-footer-text: "";     // no footer text; renders empty
```

`shared/base.scss` is rewritten to consume `$brand-primary`,
`$brand-secondary`, `$brand-accent` instead of the literal `$thd-*`
values. The SCSS load order in templates becomes:
`[cosmo, ../brand.scss, ../shared/base.scss]` — brand defaults are pulled
in **before** shared rules, so shared rules see the brand's values.

This avoids inventing a Quarto-specific `brand-mode` mechanism and keeps
the renaming purely textual (D7 records the mapping).

**Source of `pf` palette:** `/home/peter/projects/pfhome/tailwind.config.mjs`
lines 9–16, the only colour declaration in the pfhome repo. Recorded in
`brands/pf/_brand.yml` under a comment pointing at that file.

### D4 — Manifest schema: `brand:` field on `course` and `doc` entries only

```yaml
projects:
  - {type: group,  name: mk4-26, title: "Mikrocomputertechnik 4"}
  - {type: course, name: digital-und-mikrocomputertechnik,
     title: "...", group: mk4-26, lang: de, brand: thd}
  - {type: doc,    name: schutzkonzept,
     title: "...", lang: de, brand: generic}
```

- `brand:` lives on `type: course` and `type: doc` entries. **Not on
  groups** (D5).
- Validation: in `_projects.add_project` and the `modify` paths, brand
  must match the keys of `material_core/brands/`. Scanning that directory
  at startup yields the allow-list — no hard-coded list in code.
- Missing `brand:` resolves to `thd` (D1, backwards compat).

### D5 — Group landing pages stay brand-neutral

REQ-014 acceptance: "resolution rule is documented (proposed default:
landing page is brand-neutral, regardless of children)." Adopted as-is.

- No `brand:` field on `type: group` entries.
- `_landing._render_html` is unchanged. Its inline `<style>` block is
  already austere (REQ-009 §D5) — no `_brand.yml` reference, no
  `shared/` link.
- A future requirement could let landing pages adopt the `generic`
  brand's primary colour via inline CSS — explicitly not in scope here.

### D6 — `generic` brand has no logo at all

Templates currently set `favicon: THD-logo.png` and `sidebar.logo:
THD-logo.png` unconditionally. For `generic`, both keys must be **absent**
from the rendered `_quarto.yml`, not present-with-empty-string (Quarto
would emit a broken `<img src="">`).

Approach: convert the favicon / logo lines in
`templates/course/_quarto.yml`, `templates/course/slides/_quarto.yml`, and
the doc template into placeholder lines that the scaffolder either keeps
(with the brand's filename) or strips (for `generic`):

```yaml
{{LOGO_LINE}}
{{FAVICON_LINE}}
```

`_scaffold.substitute_placeholders` already handles literal substitution.
Per-brand expansion of these two placeholders happens in
`material_core/_brand_resolve.py` (D7). For `generic`, both expand to the
empty string, and a one-liner pass strips empty placeholder lines from
the rendered file (or, simpler: substitute to the comment `# (no logo)`
which Quarto ignores).

Decision: substitute to **empty string + line removal** for `generic`,
substitute to `favicon: <name>` / `  logo: <name>` for branded variants.
Avoids dangling YAML comments in user-facing files.

### D7 — `matctl link` becomes brand-aware; runs at the material repo root

Today `matctl link` runs at the repo root and creates two top-level
symlinks: `_brand.yml` → THD brand, `shared/` → shared assets. Both are
referenced from project subdirs as `../_brand.yml` and `../shared/...`.

The post-REQ-014 model:

- `shared/` symlink **stays** at repo root (brand-neutral). No change.
- `_brand.yml` at the repo root is **removed**. It cannot be a single
  symlink because different projects have different brands.
- Each project directory gets two per-project symlinks created at
  scaffold time and refreshed by a brand-aware `matctl link`:
  - `<project>/_brand.yml` → `material_core/brands/<brand>/_brand.yml`
  - `<project>/brand.scss` → `material_core/brands/<brand>/brand.scss`
- A third per-project symlink `<project>/brand-assets/` →
  `material_core/brands/<brand>/assets/` carries the logo and favicon.
  Templates reference `brand-assets/logo_pf.svg` etc.

`matctl link` semantics:

- **No argument, run at repo root:** iterate every `course`/`doc` entry
  in `projects.yml`, resolve its brand, and create the three per-project
  symlinks for each. Also create the top-level `shared/` symlink. This
  replaces the current single-shot behaviour with an idempotent fan-out.
  Existing per-project symlinks are left alone unless `--force`.
- **Run inside a project directory** (cwd matches a `course`/`doc`
  entry name): create just that project's three symlinks plus the parent
  `../shared/` if missing.

`matctl unlink` mirrors: at root, remove every per-project symlink it
recognises; in a project dir, remove just that project's three.

The acceptance criterion "running `matctl link` in a project directory
wires up the brand the project was created with" is satisfied by the
project-dir branch; the root branch is the convenient batch form for
fresh checkouts in CI.

### D8 — Scaffold-time wiring (REQ-014 v1 user-visible behaviour)

`course add` / `doc add` gain a `--brand` option:

```python
@click.option(
    "--brand",
    default="generic",
    help="Visual brand. One of: generic, thd, pf. Default: generic.",
)
```

The choice list is **dynamic** — read from `material_core/brands/`
directory entries at startup, so adding a fourth brand later is a
zero-code change. Use `click.Choice(_available_brands())` where
`_available_brands` reads `(_package_root() / "brands").iterdir()`.

After scaffolding, the new project directory gets its three brand
symlinks created in-place by the same code path that `matctl link` would
use — extracted as `_link_project(cwd, name, brand)` in `cli.py`.

### D9 — `modify --brand` switches an existing project's brand

`course modify` / `doc modify` already accept `--title` and `--group`
(REQ-008). Add `--brand <name>`:

- Validate the new brand against `_available_brands()`.
- Update `entry["brand"] = new_brand`; save manifest.
- Tear down the old per-project symlinks (`_brand.yml`, `brand.scss`,
  `brand-assets/`) and recreate them pointing at the new brand.
- Regenerate the entry's group's landing page (no-op visually for D5,
  but preserves the REQ-009 invariant uniformly).

REQ-013's "orthogonal creation" successor (currently planned, not yet
implemented) will subsume `course/doc modify`. If REQ-013 lands first,
fold `--brand` into its `set` subcommand instead. If REQ-014 lands
first, the `--brand` option moves over as part of REQ-013. Tracked as a
risk in §Risks.

### D10 — Templates carry placeholders; no per-brand template fork

REQ-014 is explicit: no per-brand templates. The single course template
serves all three brands. Brand-specific values enter via:

1. The two YAML placeholders `{{LOGO_LINE}}` and `{{FAVICON_LINE}}` (D6).
2. The brand symlinks (`_brand.yml`, `brand.scss`, `brand-assets/`)
   created post-copy (D8).

`_scaffold.substitute_placeholders` already exists; extend its
placeholder dict in `_scaffold_project` with brand-derived values.

### D11 — Footer rendering

The `$brand-footer-text` SCSS variable (D3) is consumed by a single new
rule in `shared/base.scss`:

```scss
.reveal .footer::after {
  content: $brand-footer-text;
}
```

For HTML books, an analogous rule injects the footer into the page
footer container Quarto renders. If the variable is the empty string
(`generic` brand), the rule still fires but produces no visible text —
acceptable. No conditional at the SCSS level.

### D12 — No tests committed; manual acceptance is the contract

Consistent with REQ-004..009. The acceptance run below mirrors REQ-014
§Acceptance criteria.

---

## Phase 1 — Brand registry on disk

All edits add new files under `material_core/brands/`.

- [ ] **1.1** Create `material_core/brands/thd/` and move
      `material_core/_brand.yml` into it. Adjust the `logo:` paths to
      point at `brand-assets/THD-logo.png` (the per-project symlink
      target, D7).
- [ ] **1.2** Move `material_core/shared/assets/THD-logo.png` to
      `material_core/brands/thd/assets/THD-logo.png`. Add
      `brands/thd/assets/favicon.png` as a copy (or symlink in repo —
      symlinks in package data ship correctly via `pipx`).
- [ ] **1.3** Create `material_core/brands/thd/brand.scss` with the
      `$brand-primary`, `$brand-secondary`, `$brand-accent`,
      `$brand-footer-text` defaults from D3.
- [ ] **1.4** Create `material_core/brands/generic/_brand.yml` —
      palette mirrors THD (`#1a4273`, `#e8f0f7`, `#e87722`), no
      `logo:` block, footer text empty. Drop the `typography` block
      (fonts come from `shared/`).
- [ ] **1.5** Create `material_core/brands/generic/brand.scss` with
      identical primary/secondary/accent values to `thd` and an empty
      footer string. `brands/generic/assets/` exists but stays empty.
- [ ] **1.6** Create `material_core/brands/pf/_brand.yml` — palette
      from `pfhome/tailwind.config.mjs:9-16`. Comment the source path
      at the top of the file. Logo block points at
      `brand-assets/logo_pf.svg`.
- [ ] **1.7** Copy `/home/peter/projects/pfhome/public/logo_pf.svg`
      into `material_core/brands/pf/assets/logo_pf.svg` and again as
      `favicon.svg` (or `Path.symlink_to` one to the other within the
      package data — verify `pipx install --editable` preserves
      symlinks; if not, just keep two file copies).
- [ ] **1.8** Create `material_core/brands/pf/brand.scss` with the
      warm-gold / light-warm / dark-accent values from D3 and a
      `"© Peter Fröhlich"` footer.
- [ ] **1.9** Update `pyproject.toml` `[tool.setuptools.package-data]`
      to include `brands/**/*` so the new tree ships with the package.

## Phase 2 — Refactor `shared/base.scss` to brand-neutral SCSS variables

- [ ] **2.1** Replace every literal `$thd-blue`, `$thd-blue-light`,
      `$thd-accent` reference in `material_core/shared/base.scss` with
      `$brand-primary`, `$brand-secondary`, `$brand-accent`
      respectively. Remove the local `$thd-*` declarations at the top
      of the file (they now live in each brand's `brand.scss`).
- [ ] **2.2** Add the footer rule from D11 at the bottom of
      `shared/base.scss`.
- [ ] **2.3** Manual sanity-render of an existing course in
      `/home/peter/material/` after wiring `brand.scss` symlinks
      (Phase 4) — confirm the rendered HTML still uses THD blue.
      No diff in pixel output expected for THD-branded entries.

## Phase 3 — Manifest support

All edits in `material_core/_projects.py`.

- [ ] **3.1** Extend `add_project(manifest, name, type, title, *,
      group=None, brand="generic")` — write `brand:` into the new
      entry's dict.
- [ ] **3.2** Add `available_brands(pkg_root: Path) -> list[str]` —
      sorted list of subdirectory names under `pkg_root / "brands"`.
- [ ] **3.3** Add `resolve_brand(entry: CommentedMap) -> str` —
      returns `entry.get("brand", "thd")` (the legacy fallback per
      D1).
- [ ] **3.4** Add a one-paragraph note at the top of `_projects.py`
      documenting the asymmetry between the scaffold default
      (`generic`) and the resolution default (`thd`).

## Phase 4 — `_brand_resolve.py`: per-project symlink wiring

Single new module `material_core/_brand_resolve.py`:

- [ ] **4.1** `link_project(cwd: Path, project_dir: Path, brand: str,
      pkg_root: Path, force: bool = False) -> None` — create the
      three per-project symlinks `<project_dir>/_brand.yml`,
      `<project_dir>/brand.scss`, `<project_dir>/brand-assets`
      pointing into `pkg_root/brands/<brand>/`. `force` mirrors
      `matctl link --force`.
- [ ] **4.2** `unlink_project(project_dir: Path) -> None` — remove
      the three symlinks if present and pointing into a brand dir
      (verify via `os.readlink`); leave alien files alone.
- [ ] **4.3** `relink_project(project_dir: Path, new_brand: str,
      pkg_root: Path) -> None` — convenience wrapper used by
      `modify --brand`: unlink, then link.
- [ ] **4.4** Helper `_brand_placeholders(brand: str) -> dict[str,
      str]` returning `{"{{LOGO_LINE}}": ..., "{{FAVICON_LINE}}":
      ...}` — empty strings for `generic`, branded paths otherwise.

## Phase 5 — Templates

- [ ] **5.1** Edit `templates/course/_quarto.yml`: replace
      ```yaml
        favicon:  THD-logo.png
        sidebar:
          logo:   THD-logo.png
      ```
      with
      ```yaml
        {{FAVICON_LINE}}
        sidebar:
          {{LOGO_LINE}}
      ```
      Add `../brand.scss` to the SCSS theme list **before**
      `../shared/base.scss`.
- [ ] **5.2** Same edit in `templates/course/slides/_quarto.yml` for
      the slide-level `logo:` and SCSS list.
- [ ] **5.3** Same edit in `templates/doc/_quarto.yml` (no slide
      variant for docs — they're single-file).
- [ ] **5.4** Verify no other template file mentions `THD-logo.png`
      or `_brand.yml` literally — grep:
      `grep -rn "THD-logo\|_brand\|shared/_brand" templates/`.
- [ ] **5.5** In `_scaffold.substitute_placeholders` post-pass,
      strip lines that consist solely of whitespace after
      substitution (so `{{FAVICON_LINE}}` → `""` doesn't leave a
      blank YAML key line). Implementation: split lines, drop
      lines whose `strip()` is empty *only if* they were
      originally a placeholder line — track via a sentinel, or
      simpler: do the strip unconditionally on the rendered
      `_quarto.yml` and accept that an authored blank line will
      be removed (acceptable for YAML).

## Phase 6 — CLI wiring

All edits in `material_core/cli.py`.

- [ ] **6.1** Import `available_brands`, `resolve_brand` from
      `._projects`; import `link_project`, `unlink_project`,
      `relink_project`, `_brand_placeholders` from `._brand_resolve`.
- [ ] **6.2** Add `--brand` option to `course_add`, `doc_add` with
      `default="generic"`, `type=click.Choice(available_brands(
      _package_root()))`. Pass through to `_scaffold_project`.
- [ ] **6.3** `_scaffold_project` signature gains `brand: str`. After
      `copy_template` and the existing `substitute_placeholders`
      call, merge `_brand_placeholders(brand)` into the substitution
      dict and re-run substitution on the two `_quarto.yml` files
      (`<dest>/_quarto.yml` and, for courses, `<dest>/slides/_quarto.yml`).
      Then call `link_project(cwd, dest, brand, _package_root())`.
      Then `add_project(manifest, name, type, title, group=group,
      brand=brand)`.
- [ ] **6.4** Add `--brand` option to `course_modify`, `doc_modify`.
      In the handler, if `--brand` given: validate, update entry,
      `relink_project(cwd / name, new_brand, _package_root())`.
      Combine with existing `--title` / `--group` logic — the
      "at least one flag required" check now covers three flags.
- [ ] **6.5** Rewrite `link` command per D7:
      - At repo root (cwd contains `projects.yml`): iterate
        course/doc entries, call `link_project` for each with its
        resolved brand; also create the top-level `shared` symlink
        (existing logic, scoped down — no longer touches
        `_brand.yml` at root).
      - Inside a project dir (cwd's name matches a course/doc entry):
        call `link_project(cwd.parent, cwd, brand, ...)` and ensure
        `cwd.parent / "shared"` symlink exists.
      - Detection: walk up at most one level looking for
        `projects.yml`; if found in cwd, root mode; if found in
        parent and cwd's name is a project, project-dir mode; else
        error.
- [ ] **6.6** Rewrite `unlink` command symmetrically.
- [ ] **6.7** Update the module-level constant `LINK_TARGETS = (
      "_brand.yml", "shared")` — drop `_brand.yml` (no longer at
      root); keep `shared` for the root-level symlink.

## Phase 7 — `material/` repo migration

The `material/` checkout has an existing `_brand.yml` symlink at the
repo root and existing course/doc directories without per-project
brand symlinks. After installing the new `material-core`:

- [ ] **7.1** `cd /home/peter/material && rm _brand.yml` (the
      stale root-level symlink).
- [ ] **7.2** Backfill `brand: thd` on every existing `course` /
      `doc` entry in `material/projects.yml` **except** the
      schutzkonzept entry, which gets `brand: generic` (this matches
      its real-world identity per the REQ-014 motivation).
- [ ] **7.3** `matctl link` at the repo root — fans out, creating
      per-project `_brand.yml`, `brand.scss`, `brand-assets/`
      symlinks for every course/doc.
- [ ] **7.4** `quarto render` one THD course (visual diff = none
      expected) and the schutzkonzept doc (visual diff: no logo, no
      footer text — same colours).
- [ ] **7.5** `quarto render` a throwaway PF-branded doc to verify
      the warm-gold palette and `logo_pf.svg` show up.

## Phase 8 — Documentation

- [ ] **8.1** `docs/administration.md` — add a "Brands" section
      documenting: visual-only scope (with the explicit non-list of
      out-of-scope items), `material_core/brands/<brand>/` layout,
      the three shipped brands and their intent, the `--brand`
      flag on `add` / `modify`, the `matctl link` brand resolution
      rule, and a "How to add a new brand" recipe (create a dir
      with the four files, ship in next release, no code change).
- [ ] **8.2** `docs/authoring.md` — single sentence under the
      project-creation section: "Pass `--brand thd` for THD lecture
      material; the default `generic` brand is intentionally
      neutral and suitable for personal or external documents."
- [ ] **8.3** `CLAUDE.md` — update the layout block (add `brands/`,
      remove top-level `_brand.yml`); add `--brand` to the
      `course add` / `doc add` / `course modify` / `doc modify`
      command summaries; add a one-line Current-status entry for
      REQ-014 at release time.
- [ ] **8.4** Tick acceptance criteria in
      `docs/requirements/REQ-014.md`, set `Status: DONE`, fill
      `Completed`, update `REQUIREMENTS_INDEX.md`.

## Phase 9 — Release

- [ ] **9.1** Bump `pyproject.toml` to `0.6.0` (minor — new CLI
      flags, new package data, no breaking change for users with
      existing manifests because of the resolution-default
      fallback).
- [ ] **9.2** Tag `v0.6.0`; push.
- [ ] **9.3** Update `material/.github/workflows/publish.yml`'s
      pinned `material-core` version to `v0.6.0`.
- [ ] **9.4** Push the `material/` migration commit (Phase 7) —
      includes the `projects.yml` brand backfill and the deleted
      root-level `_brand.yml` symlink.

---

## Manual acceptance run (maps to REQ-014 §Acceptance criteria)

Run in a throwaway `material` checkout.

- [ ] **A1** `ls material_core/brands/{generic,thd,pf}` — each
      contains `_brand.yml`, `brand.scss`, `assets/`. `generic/assets/`
      is empty; `thd/assets/` has `THD-logo.png` + `favicon.png`;
      `pf/assets/` has `logo_pf.svg` + `favicon.svg`. Nothing else.
- [ ] **A2** `ls material_core/shared/` — no logo, no favicon, no
      `_brand.yml`. Only `base.scss`, `typst-show.typ`, `colors.tex`,
      `assets/fonts/`.
- [ ] **A3** `matctl course add legacy-thd-course --lang de --brand
      thd` — `projects.yml` records `brand: thd`. Inside the new dir,
      three symlinks point into `brands/thd/`. `quarto render` produces
      THD-blue HTML with the THD logo in the sidebar and as favicon.
- [ ] **A4** `matctl doc add schutzkonzept-test --lang de` (no
      `--brand`) — `projects.yml` records `brand: generic`. The
      rendered HTML uses THD-blue colour but has **no logo image**, no
      favicon link, and an empty footer.
- [ ] **A5** `matctl doc add pf-test --lang de --brand pf` —
      `projects.yml` records `brand: pf`. Rendered HTML uses warm-gold
      headings, `logo_pf.svg` in the sidebar, an SVG favicon, and the
      `"© Peter Fröhlich"` footer.
- [ ] **A6** Hand-edit `projects.yml` to **remove** the `brand:` field
      from `legacy-thd-course`. Re-render — output identical to A3
      (the resolution default kicks in). This proves the
      backwards-compat clause.
- [ ] **A7** `matctl course modify legacy-thd-course --brand pf` —
      manifest now has `brand: pf`; the project's three symlinks now
      point into `brands/pf/`; `quarto render` produces the PF look.
      Switch back with `--brand thd`.
- [ ] **A8** `matctl link --force` at the repo root — every
      course/doc gets its symlinks (re)created for its current brand.
      Idempotent on a second run.
- [ ] **A9** Add `legacy-thd-course` (THD), `schutzkonzept-test`
      (generic), and `pf-test` (PF) to a single group `mixed`. Run
      `matctl group modify mixed --title "Mixed-brand group"`.
      Inspect `mixed/index.html` — it lists all three children, has no
      logo, no brand colours (REQ-009 minimal style preserved).
- [ ] **A10** `docs/administration.md` Brands section reads
      end-to-end and explains: visual-only scope, the three brands,
      how to add a fourth.
- [ ] **A11** Grep the source: `grep -rn "thd-blue\|THD-logo" material_core/`
      returns matches **only** under `material_core/brands/thd/` (and
      possibly comments in `_projects.py` documenting the legacy
      fallback). No `shared/` match.

---

## Commit strategy

`material-core`:

1. **Phase 1** — brand registry files (no behaviour change; package
   data only).
2. **Phase 2** — `shared/base.scss` refactor to brand-neutral
   variables. *Breaks rendering until Phase 4–5 land — keep the
   commit chain unbroken.*
3. **Phase 3 + 4** — manifest helpers + `_brand_resolve.py`. One
   commit; small, internal.
4. **Phase 5 + 6** — templates + CLI wiring. One commit; this is
   where the user-visible behaviour appears.
5. **Phase 8** — docs.
6. **Phase 9** — version bump + tag.

`material`:

- One migration commit: deleted root `_brand.yml`, `projects.yml`
  brand backfill, the new per-project symlinks (committed as
  symlinks since `material/` already commits its `shared` and
  `_brand.yml` symlinks).

## Risks and mitigations

- **REQ-013 collision.** REQ-013 reorganises `course/doc add` and
  `modify` into orthogonal subcommands. If REQ-013 lands first,
  REQ-014's `--brand` plugs into the new `set` subcommand (one-line
  change). If REQ-014 lands first, REQ-013's planning step inherits
  three flags instead of two — also fine. Mitigation: coordinate
  ordering when both are ready; do not block either.
- **`pipx install --editable` and symlinks within package data.**
  If `brands/pf/favicon.svg` is a symlink to `logo_pf.svg`, an
  editable install resolves it via the source tree (fine). A
  pinned-version `pipx install` from a git tag also fine — `git`
  preserves symlinks. CI runners' `pipx` follows symlinks
  transparently. If any platform balks, fall back to two file
  copies (zero functional difference, ~6 KB cost).
- **`generic` brand renders an empty footer rule.** The rule from
  D11 still emits a `::after` pseudo-element with no content; some
  themes inject vertical space anyway. Mitigation: in
  `brands/generic/brand.scss` set `$brand-footer-text: "";` and add
  a guard rule `.reveal .footer:empty { display: none; }` in
  `shared/base.scss`.
- **Quarto SCSS variable ordering.** Brand defaults must load
  before shared rules consume them. The template SCSS list
  `[cosmo, ../brand.scss, ../shared/base.scss]` (D3) ensures this.
  If a future Quarto version changes the load semantics, the
  symptom is a SCSS undefined-variable error at render time —
  loud, easy to diagnose.
- **Mixed-brand group landing pages.** D5 explicitly chooses
  brand-neutral. If the user later wants a branded landing page,
  introduce a `brand:` field on `type: group` entries in a
  follow-up. Acceptance criterion A9 verifies the current
  behaviour.
- **Schutzkonzept project doesn't yet live in `material/`.** If
  REQ-014 ships before the schutzkonzept project is migrated into
  `material/`, the `generic` brand is exercised only by the
  throwaway test in A4. Acceptable — the brand is
  spec-complete regardless of its first real consumer.
- **Logo file licensing.** `logo_pf.svg` belongs to the user; no
  third-party licence concern. THD logo usage rights are unchanged
  from today (existing arrangement carries over).

## Explicitly out of scope (deferred or covered elsewhere)

- Brand-specific Worker / domain coupling (input §5) — track as
  follow-up requirement if a need surfaces.
- Per-brand language (e.g. forcing `de` for `thd`) — REQ-010
  already separates language as a per-project flag; brands stay
  visual-only.
- Per-brand templates — explicitly forbidden by REQ-014 scope.
- Branded landing pages — D5; future requirement if needed.
- A `matctl brand list` / `matctl brand show <name>` CLI subgroup —
  nice-to-have, not required by REQ-014. Add when a fourth brand
  arrives.
- Automated brand-scope linting (e.g. CI check that
  `material_core/shared/` contains no THD strings) — manual
  inspection at review time suffices for v1.
- Backwards-compatibility shim for the deleted root-level
  `_brand.yml` symlink in `material/` — Phase 7 deletes it once;
  no rolling deprecation needed (single-user repo).
