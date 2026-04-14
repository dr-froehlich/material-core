# REQ-008 Implementation Plan — Group lifecycle, titles, and `modify`

**Goal:** Promote `group` to a first-class manifest entity (`type: group`
entries with a lifecycle), record a human-readable `title` on every
project/group entry, and add `modify` subcommands to `course`, `doc`, and
`group`. Together these close the three gaps REQ-007 left open: typo risk
on `--group`, no titles in the manifest, and no way to change a title or
group after creation.

**Context:** REQ-007 landed `group` as an optional free-text field on
course/doc entries; it is not validated against anything. Titles flow into
the scaffold but never reach `projects.yml`. REQ-009 (the auto-generated
group landing page) needs titles and needs to know which groups exist.
REQ-008 supplies both. All three requirements (007/008/009) release
together as `v0.5.0`.

**Scope boundary:** Only the pieces listed in REQ-008 §1–§7: schema
additions (`type: group`, `title`), three new `matctl group` commands,
`--title` write-through into scaffolded files, `modify` on course/doc/group
including meta-operation behaviour for `--group`, single-namespace
collision rule, and doc updates. The landing-page regeneration triggered
by these operations is **REQ-009**. Rename operations are explicitly
deferred (REQ-008 §6).

**Status tracking:** `[ ]` open · `[~]` in progress · `[x]` done

---

## Design decisions

### D1 — Single namespace enforced in `add_project` / `add_group`

REQ-008 §1 says a group, course, and doc cannot share a `name`. The
existing `add_project` already rejects on `name in project_names(doc)`;
`project_names` iterates all entries regardless of `type`, so it already
covers group entries once they exist. The new `add_group` reuses the same
check. No separate "group names" index is needed.

### D2 — `--group` existence check at the CLI boundary, not in `_projects.py`

`_projects.add_project` remains a pure data helper. The existence check —
"the group `<g>` must exist as a `type: group` entry" — sits in
`_scaffold_project` (for `add`) and in the new `modify` handlers,
alongside the existing `_NAME_RE` validation. Keeps `_projects.py` free of
business logic. A helper `group_exists(doc, name) -> bool` in
`_projects.py` is acceptable (pure lookup).

### D3 — `title` is required on every entry; default derives from slug

Today `matctl course add` defaults `title` to `title_case_from_slug(name)`
when `--title` is omitted. REQ-008 extends that: the resolved title is
also written into `projects.yml`. For `matctl group add`, `--title` is
**required** (no sensible slug-derived default for a cohort label; the
landing-page `<h1>` needs to be human-chosen). Course/doc keep the
slug-derived default so existing workflows don't break.

### D4 — Field order in manifest entries

`ruamel.yaml` preserves insertion order. REQ-007 wrote entries as
`name → type → group`. REQ-008 inserts `title` between `type` and `group`
on new entries:

```yaml
- name: esp-survival-guide
  type: doc
  title: "ESP Survival Guide"
  group: mk4-26
```

Group entries: `name → type → title` (no `group` key).

Existing entries written under REQ-007 lack `title`. They are backfilled
by hand in Phase 5 of this plan (manifest rollout), not automatically —
there is exactly one real manifest to migrate.

### D5 — Title write-through: per-type, not a uniform pair of files

REQ-008 §4 prescribes write-through to `<name>/_quarto.yml` and
`<name>/index.qmd`. The templates disagree with that uniform rule:

- **Course:** the title lives in `<name>/_quarto.yml` under `book.title`.
  `<name>/index.qmd` has its own per-page heading ("Welcome") that is
  **not** the course title and must not be touched.
- **Doc:** the title lives in `<name>/index.qmd` front matter under
  `title:`. `<name>/_quarto.yml` has no title field.

So `course modify --title` touches only `_quarto.yml:book.title`;
`doc modify --title` touches only `index.qmd` front matter. Implementation
still uses `ruamel.yaml` round-trip (for `_quarto.yml`) and a targeted
front-matter YAML rewrite for `index.qmd` (the `---` fenced block at the
top of the file). All other keys, comments, and formatting preserved.

This refines REQ-008 §4 without weakening it — matctl still owns the
`title:` key, scoped by filename, and write-through is still idempotent.
Call out the per-type targeting in the acceptance criteria and docs.

### D6 — `modify --group` composes existing atomic steps

`course/doc modify --group <new>` does not implement anything the `add`
path does not already do: validate `<new>` exists (or is the empty
string), mutate the single `group` key in the manifest entry, print the
stale-path warning. The landing-page regeneration (REQ-009) will hook
into the same seam. No cross-cutting transaction logic — a failed
validation aborts before any write; a write failure on one key is
effectively atomic because `save_manifest` rewrites the whole file.

### D7 — `--group ""` means "remove grouping"

Click's string option accepts an empty string. The handler interprets
`group is None` as "don't touch" and `group == ""` as "remove the key".
This is a two-state flag on the modify path only; on `add`, an empty
string is rejected (use no flag instead). The two cases are distinguished
by whether `--group` was passed on the command line, which Click exposes
via a sentinel default.

### D8 — Click sentinel for "flag not passed"

Click's `default=None` collapses "flag omitted" and "flag passed with
empty string" on most option shapes. For `modify`, that distinction is
load-bearing (§D7). Use a module-level sentinel object as the default,
e.g. `_UNSET = object()`, and test `group is _UNSET` vs `group == ""`.
Same pattern for `--title` on modify (omitted vs. "" — though empty title
is rejected as invalid in both `add` and `modify`).

### D9 — `modify` with no flags fails with a Click usage error

Per REQ-008 acceptance criterion "modify x with no flags fails with a
usage error". Raise `click.UsageError` (exit code 2, printed via Click's
standard path) rather than `ClickException`. Distinguishes "wrong
invocation" from "valid invocation, business-rule rejection".

### D10 — No forward-compatibility shim for REQ-009

This plan does **not** wire in landing-page regeneration calls. Every
manifest-mutating code path (add/remove/modify on course/doc/group) is
structured so REQ-009 can inject a regeneration hook at the end by
calling a single new function. No TODO comments, no empty stub — just
leave the seam at the natural place: after `save_manifest`, before the
final `click.echo`. REQ-009's plan will describe where to add the call.

### D11 — Plan includes the `material` repo edits inline

Same pattern as REQ-007: the `material` repo is the single consumer. The
manifest backfill (adding `title:` to the two existing entries) is a
one-commit rollout in `material/`, landed together with the REQ-007/009
changes as part of the batched `v0.5.0` release (tracked in REQ-009 §7).

---

## Phase 1 — Schema helpers in `_projects.py`

- [ ] **1.1** Extend `add_project(doc, name, type_, title, group=None)`:
      make `title` a required positional argument. Insert
      `entry["title"] = title` between `entry["type"]` and the optional
      `entry["group"]`. Update the one existing caller in `cli.py`.
- [ ] **1.2** Add `add_group(doc, name, title)`:
      raise `ValueError` on name collision against `project_names(doc)`;
      append an entry `{name, type: "group", title}`.
- [ ] **1.3** Add `group_exists(doc, name) -> bool`: true iff an entry
      with `type == "group"` and matching `name` exists.
- [ ] **1.4** Add `find_entry(doc, name) -> CommentedMap | None`:
      returns the raw entry by name, regardless of type. Used by the
      `modify` handlers.
- [ ] **1.5** Add `dependents_of_group(doc, group_name) -> list[str]`:
      returns the names of all `course`/`doc` entries with
      `entry.get("group") == group_name`. Used by `group remove`.
- [ ] **1.6** `remove_project` is unchanged. Add `remove_group(doc, name)`
      that also raises `ValueError` if any dependents remain (belt and
      braces — the CLI checks first, but a second line of defence is
      cheap and symmetric with `add_group`'s collision check).

## Phase 2 — CLI: `matctl group` command group

All edits in `material_core/cli.py`.

- [ ] **2.1** Add `@main.group() def group_cmd()` with function name
      `group_cmd` and Click name `"group"` (the Python name `group`
      clashes with Click's decorator).
- [ ] **2.2** `group_cmd.command("add")`:
      ```python
      @click.argument("name")
      @click.option("--title", required=True, help="Human-readable title.")
      ```
      Validate `name` against `_NAME_RE`. Reject empty `--title`. Load
      manifest, call `add_group`, save, echo "created group <name>".
      No directory creation.
- [ ] **2.3** `group_cmd.command("remove")`:
      ```python
      @click.argument("name")
      @click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
      ```
      Load manifest, find the entry, verify `type == "group"` (else fail
      with a clear error), call `dependents_of_group`. If non-empty,
      raise `ClickException` listing the dependents. Otherwise confirm
      (unless `--yes`), call `remove_group`, save, echo.
- [ ] **2.4** `group_cmd.command("modify")`:
      ```python
      @click.argument("name")
      @click.option("--title", default=_UNSET, ...)
      ```
      Only `--title` is modifiable (§REQ-008-§2). If `--title` omitted,
      raise `click.UsageError`. Reject empty string. Locate the entry,
      verify `type == "group"`, update `entry["title"]`, save, echo.

## Phase 3 — CLI: `--title` into manifest on `course add` / `doc add`

- [ ] **3.1** Extend `_scaffold_project` signature to take `title: str`
      (already resolved by the caller) and pass it through to
      `add_project(manifest, name, project_type, title, group=group)`.
- [ ] **3.2** In `_scaffold_project`, **before** the manifest mutation,
      add the group-existence check: if `group is not None`, load
      manifest first, call `group_exists(manifest, group)`, and raise
      `ClickException` if false: *"group <g> not found in projects.yml —
      create it first with `matctl group add <g> --title …`."*
- [ ] **3.3** `course_add` and `doc_add` pass `resolved_title` into
      `_scaffold_project` (already computed for placeholder
      substitution; no extra work).
- [ ] **3.4** No template changes. The scaffolded files keep their own
      `title:` fields (substituted via placeholders); the manifest now
      also records it.

## Phase 4 — CLI: `course modify` / `doc modify`

- [ ] **4.1** Add `_UNSET = object()` at module scope (reuse across
      modify handlers).
- [ ] **4.2** Add helper `_modify_project(label, name, title, group)`
      parallel to `_remove_project`:
      1. Load manifest, find entry via `find_entry`.
      2. Assert `entry["type"] == label` (course/doc); else fail with
         *"`<name>` is a `<actual-type>`, not a `<label>`"*.
      3. If `title is not _UNSET`: reject empty, update
         `entry["title"]`, write-through via `_rewrite_title(label,
         dest, title)` (see Phase 4.4).
      4. If `group is not _UNSET`:
         - If `group == ""`: delete `entry["group"]` (if present).
         - Else: validate against `_NAME_RE`, check
           `group_exists(manifest, group)`, set `entry["group"]`.
      5. If both `title is _UNSET and group is _UNSET`: raise
         `click.UsageError("specify --title and/or --group")`.
      6. `save_manifest`, echo summary. If `group` changed, echo the
         stale-path warning (same shape as `_remove_project`).
- [ ] **4.3** Add `course.command("modify")` and `doc.command("modify")`:
      ```python
      @click.argument("name")
      @click.option("--title", default=_UNSET, ...)
      @click.option("--group", default=_UNSET, ...)
      ```
      Delegate to `_modify_project("course", ...)` /
      `_modify_project("doc", ...)`.
- [ ] **4.4** Implement `_rewrite_title(label, dest, new_title)` as a
      small private helper:
      - `label == "course"`: open `dest / "_quarto.yml"` with
        `ruamel.yaml` round-trip, set `doc["book"]["title"] = new_title`,
        dump back. Validate `book` key exists (defensive; surface a
        clear error if the user hand-edited it away).
      - `label == "doc"`: rewrite the YAML front-matter block at the top
        of `dest / "index.qmd"` — split on the first two `---` lines,
        load the middle block with `ruamel.yaml`, set
        `front["title"] = new_title`, dump, rejoin. The body after the
        second `---` is preserved byte-for-byte.
      - If the target file is missing, raise `ClickException` with the
        expected path (the entry exists in the manifest but the
        scaffolded dir is gone — unusual state, worth a loud error).

## Phase 5 — `material` repo: manifest backfill

Diffs in `/home/peter/material/projects.yml`; landed as part of the
batched `v0.5.0` release (REQ-009 §7, combined commit).

- [ ] **5.1** Add `title:` to every existing entry. Two entries today
      (post-REQ-007): `digital-und-mikrocomputertechnik` and
      `esp-survival-guide`. Use the titles already in their
      `_quarto.yml` / `index.qmd`.
- [ ] **5.2** Add a top-level `type: group` entry for `mk4-26` with
      `title: "Mikrocomputertechnik 4 — WS 2026"` (or the final wording
      chosen at release time). Place it *before* its children, for
      readability; order within `projects` is semantically free but a
      group-first layout is easier to scan.
- [ ] **5.3** No workflow (`publish.yml`) edits in REQ-008 — grouping
      and deploy paths are already done by REQ-007. Landing-page deploy
      is REQ-009.

## Phase 6 — Documentation

- [ ] **6.1** `docs/administration.md §5.1` — update the manifest schema
      table: document `type: group` entries, the required `title` field
      on every entry, and the single-namespace collision rule. Update
      the worked example to show a group entry alongside its children.
- [ ] **6.2** `docs/administration.md §6 (Course Lifecycle)` and §7
      (Document Lifecycle) — add a "Modifying" subsection with the
      `matctl course modify` / `matctl doc modify` usage, including the
      `--group ""` removal case and the stale-path warning.
- [ ] **6.3** `docs/administration.md` — add a new §5.3 "Groups" or
      extend §6/§7 with the `matctl group add/remove/modify` commands
      and the "create the group before adding members" workflow.
- [ ] **6.4** `material-core/CLAUDE.md` `matctl CLI` section — add
      `matctl group add/remove/modify`, add the new `modify` subcommands
      on course/doc, and note that `--group` on `add` now requires the
      group to exist.
- [ ] **6.5** `CLAUDE.md` Current status — add REQ-008 DONE line at
      release time.

## Phase 7 — Release and close-out

Note: the `v0.5.0` tag and Worker redeploy are handled by REQ-009's
Phase 7 (batched release). REQ-008 close-out here is bookkeeping only.

- [ ] **7.1** Tick acceptance criteria in
      `docs/requirements/REQ-008.md`, set `Status: DONE`, fill
      `Completed` and `Verified by` after the manual acceptance run.
- [ ] **7.2** Update `REQUIREMENTS_INDEX.md` to match.
- [ ] **7.3** No independent tag. The release happens once at the end
      of REQ-009.

---

## Manual acceptance run (maps to REQ-008 §Acceptance criteria)

Run in a throwaway checkout of `material/` (or a scratch directory with
a minimal `projects.yml`) after Phases 1–4 are merged. REQ-009's
regeneration behaviour is not exercised here — this run verifies the
manifest and write-through only.

- [ ] **B1** `matctl group add mk4-26 --title "Mikrocomputertechnik 4"`
      — verify `projects.yml` gains a `{name, type: group, title}`
      entry; no `mk4-26/` directory is created.
- [ ] **B2** Re-run B1 — fails with a collision error.
- [ ] **B3** `matctl course add x --group mk4-26` **before** B1 was run
      — fails with "group mk4-26 not found".
- [ ] **B4** After B1, `matctl course add x --group mk4-26 --title "X"`
      — manifest entry has `name, type: course, title: "X", group:
      mk4-26`, in that order.
- [ ] **B5** `matctl course add y` — manifest entry has
      `title: "Y"` (title-cased slug).
- [ ] **B6** `matctl course add mk4-26` — fails (name collides with
      existing group). Likewise `matctl group add x` after B4 fails.
- [ ] **B7** `matctl group remove mk4-26` with children present —
      fails, lists `x`.
- [ ] **B8** `matctl course remove x --yes`, then
      `matctl group remove mk4-26 --yes` — succeeds.
- [ ] **B9** `matctl group modify mk4-26 --title "New"` — updates
      manifest title only.
- [ ] **B10** `matctl course modify x --title "New Title"` — `title` in
      `projects.yml` and `x/_quarto.yml:book.title` both updated;
      `x/index.qmd` unchanged (per-page "Welcome" heading preserved);
      all other keys, comments, and whitespace in `_quarto.yml`
      preserved.
- [ ] **B11** `matctl doc modify d --title "New Title"` — `title` in
      `projects.yml` and `d/index.qmd` front matter updated; body of
      `index.qmd` and `_quarto.yml` unchanged.
- [ ] **B12** `matctl course modify x --group mk4-27` (with `mk4-27`
      existing) — `group` key updated; stale-path warning printed.
- [ ] **B13** `matctl course modify x --group ""` — `group` key
      removed entirely from the entry.
- [ ] **B14** `matctl course modify x` (no flags) — Click usage error,
      exit code 2.
- [ ] **B15** `matctl doc modify d --group …` — analogous to course
      behaviour.

---

## Commit strategy

`material-core`:

1. **Phase 1** — `_projects.py` schema helpers. One focused commit;
   no behaviour change yet because `cli.py` still uses the old
   `add_project` signature. Land together with Phase 3.1 to keep tests
   green.
2. **Phases 2–4** — CLI commands (`group` subcommands, `--title` into
   manifest, `modify` handlers, title write-through). Can split into
   `group` subcommand + `modify` if the diff gets big; otherwise single
   commit.
3. **Phase 6** — documentation. Separate so doc-only review stays
   light.
4. **Phase 7** — REQ status + index. No tag (batched into REQ-009's
   release).

`material` (backfill): single commit at release time, bundled with the
REQ-009 rollout per REQ-009 §7.

## Risks and mitigations

- **Front-matter rewrite in `index.qmd` corrupts the file.** The
  `---`-fenced YAML block is conventional but not enforced by Quarto.
  Mitigation: in `_rewrite_title`, match only on a leading `---\n`
  followed by a balanced closing `---\n`; if either is absent, raise a
  clear error asking the user to fix the file by hand and re-run. Do
  not attempt to synthesize a front-matter block.
- **`_quarto.yml` lacks `book:` (doc template, or hand-edited course).**
  `_rewrite_title("course", ...)` guards with a clear error rather than
  auto-inserting keys. A hand-edited course that has moved `title:` out
  of `book:` is a structure matctl does not recognize.
- **Partial write on manifest mutation.** `save_manifest` writes the
  whole file in one `open("w")` call. A crash mid-write leaves a
  truncated file. Mitigation is the same as it already is for the REQ-007
  code paths: none, because the cost of atomic-replace plumbing exceeds
  the realistic failure rate on a developer laptop. Note for future work
  if matctl ever runs in CI.
- **Collision rule surprises.** REQ-008 §1 says a group, course, and doc
  share one namespace. The implementation piggybacks on the existing
  `name in project_names(doc)` check which already enumerates *all*
  entry types. Verified by acceptance test B6.
- **`--group ""` sentinel collision.** If a user literally passes
  `--group ""` on `add` (not `modify`), Click sees the empty string and
  `_scaffold_project` validates it via `_NAME_RE` which rejects empty
  strings. Result: a clean validation error, not a silent "no group"
  record. Acceptance test coverage implicit in B4/B5.
- **Title write-through on a project whose directory has been removed.**
  `_rewrite_title` raises with the expected path. This can only happen
  if the manifest and filesystem have drifted (user hand-removed the
  dir). Loud error is the right behaviour.

## Explicitly out of scope (deferred or covered elsewhere)

- Auto-generated `<group>/index.html` landing page and its regeneration
  triggers → **REQ-009**.
- Renaming a group/course/doc (changing `name`) → deferred, open as a
  separate requirement when needed (REQ-008 §6 describes the composition
  path in the meantime).
- Backfilling existing manifests automatically → manual, one-time, done
  in Phase 5.
- Promoting `subtitle` to the manifest → out of scope (REQ-008 §Notes).
- Tag bump and Worker redeploy → happens once at the end of REQ-009
  (batched `v0.5.0` release).
