# REQ-004 Implementation Plan — `matctl course add` / `matctl course remove`

**Goal:** Replace the manual "copy an existing course directory, edit
`_quarto.yml`, edit `projects.yml`" ritual with two CLI commands that make
adding and removing a course a single-invocation operation:

```
matctl course add <name> [--title "Human readable title"] [--subtitle "Optional subtitle"]
matctl course remove <name> [--yes]
```

**Context:** REQ-003 gave us `projects.yml` as a stable, manifest-shaped
surface that CI reads on every push. Hand-editing it works but is error-prone
(whitespace, ordering, accidentally clobbering comments), and the course
template still carries `# CHANGE` placeholder comments that a human is
expected to find and edit. REQ-004 closes that loop: `course add` patches
the manifest, copies the template, and substitutes the declared placeholders
in one shot. `course remove` is its inverse for local cleanup.

**Scope boundary:** Courses only. Standalone documents (`type: doc`) are
REQ-005 and will reuse the same plumbing (`ruamel.yaml` patcher, placeholder
substitution helper, manifest guard). Design the internals with that reuse in
mind — a private helper module, not inline logic in the `course` subcommand.

**Status tracking:** `[ ]` open · `[~]` in progress · `[x]` done

---

## Design decisions

### D1 — YAML round-trip: `ruamel.yaml`

`projects.yml` today has one entry and no comments, but REQ-003 explicitly
reserved the right to grow it (per-project overrides, access-gate flags,
etc.), and the administration docs already tell humans they may add comments
there. `PyYAML` reformats on write and silently drops comments; `ruamel.yaml`
in round-trip mode preserves both. Cost is one dependency; benefit is that
`matctl course add` can never silently mangle a hand-edited manifest. Pinned
loosely (`ruamel.yaml>=0.18,<0.19`) — the 0.18 line is stable and the API we
need (`YAML(typ="rt")`, `.load`, `.dump`) is frozen.

### D2 — Placeholder substitution: declared tokens, plain string replace

The template currently carries `# CHANGE` comment annotations on hand-edit
spots (title, subtitle, footer, PDF output filename). REQ-004 replaces those
with explicit `{{COURSE_NAME}}` / `{{COURSE_TITLE}}` / `{{COURSE_SUBTITLE}}`
tokens and does a plain `str.replace` pass after copying. No Jinja, no
`string.Template` — the template stays readable as Quarto input on its own
(a human can still open `material_core/templates/course/_quarto.yml` and see
valid YAML with token strings in a handful of values), and there is zero
escaping surface.

The three placeholders are:

| Token | Source | Default |
|---|---|---|
| `{{COURSE_NAME}}` | positional `<name>` arg | — (required) |
| `{{COURSE_TITLE}}` | `--title` option | `<name>` with dashes → spaces, title-cased |
| `{{COURSE_SUBTITLE}}` | `--subtitle` option | empty string (see below) |

`--subtitle` defaults to the empty string. When empty, the substitution
pass still runs — the token is replaced with `""` — and Quarto's `subtitle:
""` renders as no subtitle in HTML and PDF output. We deliberately do *not*
delete the `subtitle:` key from `_quarto.yml` when the subtitle is empty:
keeping a stable YAML shape is worth more than shaving one line, and the
user who later wants to add a subtitle can edit one value instead of
re-learning the schema. Verified during Phase 1.3 smoke render.

### D3 — Failure-mode idempotency, not transactional rollback

Both commands validate everything they can *before* any mutation, then do
the writes in an order where a crash mid-operation leaves the tree
recoverable by re-running either the same command (after cleanup) or its
inverse. Specifically, `course add`:

1. Validates preconditions (manifest exists, target dir does not exist,
   name is not already in the manifest, name is a valid directory name).
2. Copies the template tree to `./<name>/` **first**.
3. Runs the in-place token substitution on the copied tree.
4. Patches `projects.yml` **last**.

If step 2 crashes mid-copy, `./<name>/` exists partially; the user runs
`matctl course remove <name> --yes` (which tolerates a missing manifest
entry — see §D4) or deletes the directory by hand and retries. If step 4
crashes, the directory is complete but not registered; re-running `course
add` hits the "target dir already exists" check, so we document the recovery
explicitly: remove the dir and retry, or add the manifest line manually.
This is cheap to implement and matches the acceptance criteria without
requiring a real transaction.

### D4 — `course remove` tolerates asymmetric state

Strict interpretation of the requirement ("refuses to run if `./<name>/`
does not exist in the manifest") would prevent cleaning up the
partial-failure case above. The implementation treats the manifest entry
and the directory as independent pieces of state: `course remove` reports
which pieces it found and removes whichever are present, and only errors
out if **neither** exists. This is the only place the implementation
deviates from a literal reading of the requirement; it is called out here
so the acceptance-criteria check in Phase 6 is not surprised by it.

### D5 — Stub cleanup is part of this requirement, not a follow-up

`material_core/cli.py` still carries `render`, `deploy`, `new` as
`NotImplementedError` stubs from the REQ-001 split. REQ-004 deletes them.
Rationale recorded in the requirement: `render`/`deploy` were explicitly
rejected when REQ-002 was promoted, and `new` is superseded by
`course add` / `doc add`. Keeping the stubs around advertises commands that
will never ship, which is worse than a clean `matctl --help` that only
lists real commands.

---

## Phase 1 — Template placeholder audit

Before any CLI code, lock down the template so the substitution pass has a
known set of tokens to replace.

- [ ] **1.1** Replace `# CHANGE` placeholders in
      `material_core/templates/course/` with declared tokens:
  - `_quarto.yml`: `title: "{{COURSE_TITLE}}"`, `subtitle:
    "{{COURSE_SUBTITLE}}"` (kept as a stable key; empty string when the
    user does not pass `--subtitle`), `output-file:
    {{COURSE_NAME}}.pdf`.
  - `slides/_quarto.yml`: `footer: "{{COURSE_TITLE}} — Prof. Dr.-Ing.
    Peter Fröhlich"`.
  - `slides/01-introduction.qmd`: `subtitle: "{{COURSE_TITLE}}"`.
- [ ] **1.2** Grep the template tree for any remaining `CHANGE`,
      `course-name`, or `Course Title` strings; expect zero hits.
- [ ] **1.3** Hand-substitute the tokens in a scratch copy
      (`/tmp/scaffold-smoke/demo-course/`) — run the smoke render
      **twice**: once with a non-empty subtitle value, once with
      `{{COURSE_SUBTITLE}}` → `""`. Both must build clean via `quarto
      render demo-course` + `quarto render demo-course/slides`, and the
      empty-subtitle render must show no stray "Subtitle" text in the
      HTML/PDF. This is the "template is still valid after tokenization"
      gate — it must pass before writing any Python.
- [ ] **1.4** Commit Phase 1 on its own. The template edit is independent
      of the CLI work and a good rollback point if the CLI work needs to
      be reverted.

## Phase 2 — Add `ruamel.yaml` dependency

- [ ] **2.1** Add `"ruamel.yaml>=0.18,<0.19"` to
      `pyproject.toml [project].dependencies`.
- [ ] **2.2** `pipx install --editable /home/peter/projects/material-core`
      to pick up the new dependency. Confirm `python -c "from ruamel.yaml
      import YAML; YAML(typ='rt')"` runs clean inside the pipx venv.
- [ ] **2.3** No commit yet — fold this into the Phase 3 commit so `main`
      never carries an unused dependency.

## Phase 3 — Implement `material_core/_projects.py`

A small private helper module. Not exported. REQ-005 will import the same
functions for the `doc` variant, so keep the surface minimal and
type-agnostic.

- [ ] **3.1** Create `material_core/_projects.py` with:
  - `PROJECTS_FILE = "projects.yml"` (relative — callers always pass the
    CWD-anchored `Path`).
  - `load_manifest(path: Path) -> CommentedMap` — returns the
    `ruamel.yaml` round-trip document. Raises `click.ClickException` with
    a clear message if the file does not exist ("not in a material
    checkout: projects.yml not found").
  - `save_manifest(path: Path, doc: CommentedMap) -> None` — writes back
    with `YAML(typ="rt")` defaults (indent 2, block style).
  - `project_names(doc) -> list[str]` — pulls `[p["name"] for p in
    doc["projects"]]`.
  - `add_project(doc, name: str, type_: str) -> None` — appends
    `{"name": name, "type": type_}` to `doc["projects"]`. Raises
    `ValueError` if `name` is already present (caller translates to
    `ClickException`).
  - `remove_project(doc, name: str) -> bool` — removes the entry by name;
    returns `True` if something was removed, `False` if not (caller
    decides whether that is an error, per §D4).
- [ ] **3.2** Create `material_core/_scaffold.py` with:
  - `PLACEHOLDERS = ("{{COURSE_NAME}}", "{{COURSE_TITLE}}",
    "{{COURSE_SUBTITLE}}")` — a tuple so REQ-005 can extend it rather
    than duplicate.
  - `copy_template(template_subdir: str, dest: Path) -> None` — uses
    `importlib.resources.files("material_core") / "templates" /
    template_subdir` and `shutil.copytree` with `dirs_exist_ok=False`.
    Wraps `FileExistsError` as a friendlier message.
  - `substitute_placeholders(root: Path, values: dict[str, str]) -> None`
    — walks the tree, reads each file as text (skip any file that fails
    UTF-8 decode — binary assets under `assets/diagrams` pass through),
    runs `str.replace` for each `(token, value)`, writes back only if the
    content changed. Binary skip keeps `assets/diagrams/*` safe without
    an extension allowlist.
- [ ] **3.3** Add `title_case_from_slug(name: str) -> str` in
      `_scaffold.py`: `name.replace("-", " ").replace("_", " ").title()`.
      Used for the `--title` default.
- [ ] **3.4** No tests in the formal sense — this repo has none today,
      and adding pytest scaffolding is out of scope for REQ-004. Coverage
      comes from the Phase 5 manual acceptance run.

## Phase 4 — Wire `matctl course add` / `course remove`

- [ ] **4.1** In `material_core/cli.py`, add a `course` click group under
      `main`: `@main.group()` named `course`, docstring "Manage courses in
      a material checkout."
- [ ] **4.2** `course add`:
  ```python
  @course.command("add")
  @click.argument("name")
  @click.option("--title", default=None, help="Human-readable title "
                "(default: <name> title-cased).")
  @click.option("--subtitle", default="", help="Optional subtitle "
                "(default: empty).")
  def course_add(name: str, title: str | None, subtitle: str) -> None: ...
  ```
  Flow:
  1. Validate `name` is a plausible directory component
     (`re.fullmatch(r"[a-z0-9][a-z0-9._-]*", name)`). Fail early otherwise
     — prevents `course add ../etc`.
  2. `cwd = Path.cwd()`; `manifest_path = cwd / "projects.yml"`.
  3. `doc = load_manifest(manifest_path)` (fails if missing).
  4. If `name in project_names(doc)`: `ClickException` "already
     registered in projects.yml".
  5. `dest = cwd / name`; if `dest.exists()`: `ClickException`.
  6. `copy_template("course", dest)`.
  7. `substitute_placeholders(dest, {"{{COURSE_NAME}}": name,
     "{{COURSE_TITLE}}": title or title_case_from_slug(name),
     "{{COURSE_SUBTITLE}}": subtitle})`.
  8. `add_project(doc, name, "course"); save_manifest(manifest_path, doc)`.
  9. Print the summary + next-steps (preview / commit / push).
- [ ] **4.3** `course remove`:
  ```python
  @course.command("remove")
  @click.argument("name")
  @click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
  def course_remove(name: str, yes: bool) -> None: ...
  ```
  Flow:
  1. Load manifest (fails if missing).
  2. `dir_exists = (cwd / name).exists()`;
     `in_manifest = name in project_names(doc)`.
  3. If neither: `ClickException` "nothing to remove".
  4. If `dir_exists` and not `yes`: `click.confirm` asking to delete
     `./<name>/`. Abort on no.
  5. If `in_manifest`: `remove_project(doc, name);
     save_manifest(...)`.
  6. If `dir_exists`: `shutil.rmtree(cwd / name)`.
  7. Print a summary stating which pieces were removed, plus the
     standing reminder from the requirement: remote content at
     `material.professorfroehlich.de/<name>/` and any issued access
     tokens are **not** touched by this command — see
     `administration.md` for the manual cleanup.
- [ ] **4.4** Delete the `render`, `deploy`, and `new` stub commands from
      `cli.py` (decision D5). Drop any `click` imports that become unused.
- [ ] **4.5** `matctl --help` shows exactly `link`, `unlink`, `course`.
      `matctl course --help` shows `add`, `remove`. Nothing else.

## Phase 5 — Manual acceptance run in a real `material` checkout

All steps run in `/home/peter/material/` against the live checkout. The
acceptance criteria map directly to these steps.

- [ ] **5.1** `matctl course add demo-course --subtitle "Spring 2026"`
      — expect `./demo-course/` created with placeholders substituted.
      Verify: `grep -R "{{COURSE" demo-course/` returns zero hits;
      `grep -R "Demo Course" demo-course/` hits `_quarto.yml` title and
      `slides/_quarto.yml` footer; `grep -R "Spring 2026" demo-course/`
      hits the `_quarto.yml` subtitle line. Also run a second scaffold
      as `matctl course add demo-course-bare` with no `--subtitle`; the
      resulting `_quarto.yml` should contain `subtitle: ""` and render
      cleanly with no visible subtitle in the HTML/PDF output.
- [ ] **5.2** `cat projects.yml` — new entry `{name: demo-course, type:
      course}` appended, existing entry and any comments intact. Compare
      against `git diff projects.yml` — the diff must be a clean addition,
      no reformatting of the unrelated line.
- [ ] **5.3** `quarto render demo-course` and `quarto render
      demo-course/slides` — both succeed with no manual edits. Open the
      HTML and PDF, eyeball the title and footer strings.
- [ ] **5.4** `matctl course add demo-course` a second time — expect
      `ClickException` "already exists" (or "already registered" — either
      precondition can trip first depending on which check runs first;
      both are fine as long as nothing is mutated). Confirm
      `git status projects.yml demo-course/` shows no additional changes.
- [ ] **5.5** `matctl course add ../escape` and `matctl course add
      weird name` — both fail on the name-validation check. No
      filesystem or manifest changes.
- [ ] **5.6** `matctl course remove nonexistent` — clean "nothing to
      remove" error, no changes.
- [ ] **5.7** `matctl course remove demo-course --yes` — directory and
      manifest entry both gone. `git status` is clean (back to the
      pre-5.1 state modulo untracked `_output/` dirs from the render).
- [ ] **5.8** Asymmetric-state recovery check: manually create an empty
      `./orphan/` directory, then run `matctl course remove orphan --yes`.
      Expect the directory to be removed without error, with a note that
      no manifest entry was present. This exercises §D4.

## Phase 6 — Documentation updates

- [ ] **6.1** `material-core/docs/administration.md §6.2` ("Adding a new
      course"): replace the manual copy/edit ritual with:
      1. `matctl course add <name> --title "..."` in the `material`
         checkout.
      2. Commit the new directory + `projects.yml` change.
      3. Push. CI (REQ-003 matrix) picks up the new project.
      Keep a short "what `course add` does under the hood" paragraph
      cross-referencing the manifest schema described in the REQ-003
      section. Add a "Removing a course" paragraph pointing at
      `matctl course remove`, and explicitly list the pieces that are
      **not** cleaned up (remote content, access tokens, KV entries).
- [ ] **6.2** `/home/peter/material/CLAUDE.md`: update the "starting a
      new course" section to point at `matctl course add`. If the section
      does not exist yet, add a short one under the existing workflow
      notes.
- [ ] **6.3** `material-core/CLAUDE.md`: the "matctl CLI" block lists
      `render`, `deploy`, `new` as REQ-002 stubs. Replace that list with
      the real commands (`course add`, `course remove`) and delete the
      stub section.

## Phase 7 — Close out REQ-004

- [ ] **7.1** Tick acceptance criteria in `docs/requirements/REQ-004.md`,
      set `Status: DONE`, fill `Completed` (`2026-04-??`) and
      `Verified by` (e.g. "manual scaffold + render + remove in
      /home/peter/material 2026-04-??").
- [ ] **7.2** Update `REQUIREMENTS_INDEX.md` to match.
- [ ] **7.3** Tag a new `material-core` release (`v0.2.0` — new command
      group is a minor bump per the semver rule in `CLAUDE.md`). Bump
      the pinned ref in `material/.github/workflows/publish.yml`
      accordingly so CI pulls the version that understands `course add`.
      Commit that bump in `material`.
- [ ] **7.4** REQ-005 is now unblocked. `_projects.py` and `_scaffold.py`
      are the shared surface it will extend with a `doc` template and a
      `matctl doc add` / `doc remove` group.

---

## Commit strategy

Three commits in `material-core`, one in `material`:

1. **Phase 1** — template tokenization only. Self-contained, reversible,
   doesn't depend on any new Python.
2. **Phases 2–4** — `ruamel.yaml` dep + `_projects.py` + `_scaffold.py` +
   `cli.py` wiring + stub removal. All touch each other, ships as one
   commit.
3. **Phase 6** — documentation. Could fold into commit 2, but keeping it
   separate makes the code review of commit 2 narrower.
4. **`material` repo** — the `CLAUDE.md` update from 6.2 + the pinned-ref
   bump from 7.3. One commit, message references REQ-004.

## Risks and mitigations

- **`ruamel.yaml` reformats the unrelated `digital-und-mikrocomputertechnik`
  line on save.** Mitigation: Phase 5.2 explicitly diffs `projects.yml`
  and fails the phase if anything beyond the new line changes. If it
  trips, fall back to `YAML()` defaults tuning (`yaml.preserve_quotes =
  True`, `yaml.indent(mapping=2, sequence=4, offset=2)`) before
  considering a different library.
- **`importlib.resources` returns a `MultiplexedPath` when the package is
  installed in a zip.** `pipx` installs flat, and the existing `link`
  command already uses `files("material_core")` successfully, so this is
  not a realistic risk in our deployment — but if a future install mode
  changes that, `copy_template` should grow a fallback that materializes
  the path via `as_file()`. Not worth implementing preemptively.
- **Binary files in `assets/diagrams/` crash the UTF-8 decode step.**
  Mitigation is the `try/except UnicodeDecodeError: continue` skip
  described in 3.2. Verified by 5.3 (the render would fail if a diagram
  asset got corrupted).
- **User has uncommitted changes in `projects.yml` when running `course
  add`.** Out of scope — `matctl` is not a VCS tool and should not
  second-guess the user's working copy. The Phase 6 docs mention
  committing as a follow-up step, which is the right place for that
  reminder.

## Explicitly out of scope (deferred to later REQs)

- `matctl doc add` / `doc remove` — REQ-005. Shares `_projects.py` and
  `_scaffold.py` but needs its own template and a different render-rule
  branch in CI.
- Cleaning up Cloudflare Worker KV tokens issued against a removed
  course — deferred per the REQ-004 notes; future token-management REQ.
- Removing remote content under `material.professorfroehlich.de/<name>/`
  — deliberately manual, documented in `administration.md`.
- Richer template variables (course code, term, author override) —
  requirement explicitly says to promote to a new REQ if needed rather
  than expanding `--title`.
- Test suite for `_projects.py` / `_scaffold.py` — this repo has no
  pytest harness today; adding one is its own requirement.
