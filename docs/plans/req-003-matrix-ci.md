# REQ-003 Implementation Plan — Matrix-driven CI with `projects.yml`

**Goal:** Replace the hand-maintained per-course job blocks in
`material/.github/workflows/publish.yml` with a single matrix-driven `build`
job that reads an explicit manifest, `material/projects.yml`. Adding a course
or doc becomes: edit `projects.yml`, create the directory. No workflow edits.

**Context:** Today, adding a project requires editing three coordinated spots
in `publish.yml` (the `changes` job outputs, the `paths-filter` filters, a full
copy of the render/deploy job). REQ-004 and REQ-005 need a stable, scriptable
surface to patch so `matctl course add` / `matctl doc add` can register new
projects without touching YAML workflow internals. `projects.yml` is that
surface.

**Scope boundary:** This requirement changes the workflow and introduces
`projects.yml`. It does **not** touch `matctl` itself — `matctl course add`
lives in REQ-004 and will be the first real consumer of the manifest.

**Status tracking:** `[ ]` open · `[~]` in progress · `[x]` done

---

## Design decision — change detection strategy

The target workflow needs one piece of non-trivial logic: given a push, decide
which projects in the manifest have changed files under their directories.
Three options were considered:

| Option | Mechanics | Verdict |
|---|---|---|
| **A. `dorny/paths-filter` with a dynamically-generated filter YAML** | A shell step reads `projects.yml`, emits a temporary filter file, passes it to `paths-filter`, then reads the per-project outputs back into a JSON array. | Rejected — two-stage transform (manifest → filter YAML → outputs → JSON) for a job that only needs a list of changed paths. The indirection through `paths-filter` earns nothing once the filters come from a manifest anyway. |
| **B. `git diff` against the push base** | One shell step: compute the changed file list from `${{ github.event.before }}..${{ github.sha }}` (or the PR base), loop over projects in `projects.yml`, emit projects whose prefix matches any changed file. | **Chosen** — ~20 lines of shell + `yq`, no third-party action, single source of truth. |
| **C. Always build everything, no change detection** | Drop the `changes` job entirely. | Rejected — acceptance criterion requires unrelated pushes to build nothing. Also wasteful as the manifest grows. |

**How Option B works:**

- The `changes` job runs `actions/checkout@v4` with `fetch-depth: 0` (or `2`
  if `github.event.before` is reliably present — it is for `push` events on
  non-force-pushes; force pushes and `workflow_dispatch` fall through to the
  "build everything" branch below).
- A single step installs `yq` (pre-installed on `ubuntu-latest`), extracts
  project names from `projects.yml`, diffs `HEAD` against the push base, and
  for each project emits it if any changed file starts with `<name>/`.
- The step also short-circuits on `workflow_dispatch` and on the first push
  after a force-push (no valid `before`): it emits every project in the
  manifest. This keeps the manual-dispatch acceptance criterion trivial and
  makes force-push recovery safe rather than silently no-op.
- Output: a JSON array like `["digital-und-mikrocomputertechnik"]`, consumed
  by `strategy.matrix.project` in the `build` job.
- The `build` job is guarded by `if: needs.changes.outputs.projects != '[]'`
  so unrelated pushes skip cleanly instead of failing on an empty matrix.

**Why this is safe:**

- `yq` is pre-installed on GitHub's `ubuntu-latest` runners — no extra install
  step, no version pinning drift.
- The changed-files computation is a pure function of `git diff` output, so
  it's locally reproducible: `git diff --name-only <before>..HEAD` is easy to
  eyeball while debugging a failed CI run.
- The "build everything" fallback for `workflow_dispatch` and missing-base
  cases is strictly the safe default — we never silently skip a project that
  might have changed.

---

## Phase 1 — Author `projects.yml` in `material`

- [ ] **1.1** Create `/home/peter/material/projects.yml` with the current
      single course registered:
      ```yaml
      projects:
        - name: digital-und-mikrocomputertechnik
          type: course
      ```
- [ ] **1.2** Sanity-check with `yq '.projects[].name' projects.yml` locally.
- [ ] **1.3** Do **not** commit yet — the workflow rewrite in Phase 2 lands in
      the same commit so `main` is never in a state where `projects.yml`
      exists but the workflow still hard-codes jobs (or vice versa).

## Phase 2 — Rewrite `material/.github/workflows/publish.yml`

All edits happen on a throwaway branch in `material/`. No changes to
`material-core`.

- [ ] **2.1** Replace the `changes` job with a manifest-driven version:
  - `runs-on: ubuntu-latest`
  - `outputs.projects: ${{ steps.compute.outputs.projects }}`
  - Checkout with `fetch-depth: 0`
  - Single `compute` step that:
    1. Reads all project names: `yq -o=json '.projects[].name' projects.yml`
    2. Decides the change set:
       - On `workflow_dispatch`: every project in the manifest.
       - On `push` with a valid `github.event.before` that is not
         `0000000000000000000000000000000000000000` (force-push sentinel):
         diff `before..sha`, include a project if any changed path starts
         with `<name>/` **or** the path is `projects.yml` or
         `.github/workflows/publish.yml` (workflow edits rebuild everything).
       - Otherwise (force-push, first commit, missing base): every project.
    3. Emits `projects=<json-array>` via `$GITHUB_OUTPUT`.
- [ ] **2.2** Replace all per-course job blocks with one `build` job:
  - `needs: changes`
  - `if: needs.changes.outputs.projects != '[]'`
  - `strategy.fail-fast: false`
  - `strategy.matrix.project: ${{ fromJson(needs.changes.outputs.projects) }}`
  - Env: `PROJECT: ${{ matrix.project }}`
- [ ] **2.3** Inside the `build` job, carry forward verbatim from the old
      per-course block:
  - `actions/checkout@v4`
  - `actions/setup-python@v5` (Python 3.12)
  - `pipx install "git+https://github.com/dr-froehlich/material-core@${MATERIAL_CORE_REF}"`
  - `matctl link`
  - `quarto-dev/quarto-actions/setup@v2`
  - Font install step (unchanged)
- [ ] **2.4** Add a **"Resolve project type"** step that reads the matrix
      project's `type` from `projects.yml`:
      `TYPE=$(yq -r ".projects[] | select(.name == \"$PROJECT\") | .type" projects.yml)`
      and exports `PROJECT_TYPE` to the job env.
- [ ] **2.5** Render step — one `run:` block, branch on `$PROJECT_TYPE`:
      ```bash
      case "$PROJECT_TYPE" in
        course)
          quarto render "$PROJECT"
          quarto render "$PROJECT/slides"
          ;;
        doc)
          quarto render "$PROJECT"
          ;;
        *)
          echo "Unknown project type: $PROJECT_TYPE" >&2
          exit 1
          ;;
      esac
      ```
- [ ] **2.6** Deploy step — same `case` on `$PROJECT_TYPE`:
  - `course`: deploy `${PROJECT}/_output/book/*` to `${WEBROOT}/`, then
    `${PROJECT}/slides/_output/*` to `${WEBROOT}/slides/` (existing
    `mkdir -p` + `scp` logic, unchanged except for `COURSE_DIR` → `PROJECT`).
  - `doc`: deploy `${PROJECT}/_output/*` to `${WEBROOT}/`. No slides path.
  - `WEBROOT="/material.professorfroehlich.de/httpdocs/${PROJECT}"` — same as
    before, just renamed variable.
- [ ] **2.7** Delete the old per-course job block and the `# Add new courses
      below…` trailing comment.

## Phase 3 — Local dry-run of the change-detection logic

Before pushing to GitHub, verify the `compute` shell logic works on the real
repo state.

- [ ] **3.1** Extract the `compute` step's shell body into a local script and
      run it in `/home/peter/material/` against a known commit range:
  - `GITHUB_EVENT_NAME=push BEFORE=HEAD~1 SHA=HEAD ./compute.sh` — expect
    `["digital-und-mikrocomputertechnik"]` when the last commit touched that
    directory.
  - `GITHUB_EVENT_NAME=push BEFORE=HEAD~1 SHA=HEAD ./compute.sh` on a commit
    that touched only `README.md` — expect `[]`.
  - `GITHUB_EVENT_NAME=workflow_dispatch ./compute.sh` — expect every project
    in the manifest.
  - Simulate force-push: `BEFORE=0000000000000000000000000000000000000000` —
    expect every project.
- [ ] **3.2** Fix any edge cases before committing (empty manifest, project
      names with special characters — expect none today, but the `yq`
      extraction should not silently misquote).

## Phase 4 — Commit, push, observe

- [ ] **4.1** In `material/`, commit `projects.yml` + the rewritten
      `publish.yml` in a single commit with a message referencing REQ-003.
- [ ] **4.2** Push to a throwaway branch first (not `main`). Open a PR so the
      workflow runs on the branch and the Actions log is inspectable without
      touching production.
- [ ] **4.3** In the PR check:
  - `changes` job output matches expectation (the branch touched
    `digital-und-mikrocomputertechnik/...`? it should appear in the array).
  - `build` matrix expands correctly.
  - Render + deploy succeed end-to-end. (Deploy **will** write to Netcup —
    that is fine, the target directory is the same as production and the
    content for this project is not student-facing yet.)
- [ ] **4.4** Merge to `main`. Confirm the post-merge run also succeeds.

## Phase 5 — Acceptance-criteria verification

Run these explicit tests against `material` after merge. Each maps to an
acceptance criterion in `REQ-003.md`.

- [ ] **5.1** Push an unrelated change (touch `README.md`) to a branch; confirm
      `changes.outputs.projects == '[]'` and the `build` job is skipped
      entirely (no matrix expansion, no error).
- [ ] **5.2** Run `workflow_dispatch` manually from the Actions UI; confirm
      every project in the manifest is built.
- [ ] **5.3** Add a sham second project to `projects.yml` (e.g.
      `name: scratch-test, type: doc`) and create `material/scratch-test/`
      with a minimal `_quarto.yml` + `index.qmd`. Push. Confirm the workflow
      picks it up with **no workflow-file edits**. Revert the sham project
      after the check (do not ship it).
- [ ] **5.4** Visually inspect the deployed
      `material.professorfroehlich.de/digital-und-mikrocomputertechnik/` —
      HTML, PDF, slides — against the pre-matrix state. No regression.
- [ ] **5.5** Issue, validate, and revoke a throwaway token via
      `manage-tokens.sh`. Confirm the access path is unaffected.

## Phase 6 — Documentation

- [ ] **6.1** Update `material-core/docs/administration.md §6.2` ("Adding a
      new course"): the new flow is
      1. Edit `material/projects.yml` — add a `{name, type}` entry.
      2. Create the project directory with its `_quarto.yml`.
      3. Commit. Done. No workflow edits.
      Remove the "copy the job block" instructions.
- [ ] **6.2** Add a short "Manifest: `projects.yml`" subsection to
      `administration.md` describing the schema (`name`, `type ∈ {course,
      doc}`) and the render/deploy rules each type triggers.
- [ ] **6.3** Note in the same section that `matctl course add` / `doc add`
      (REQ-004, REQ-005) will patch this file automatically; hand-editing is
      the interim flow.

## Phase 7 — Close out REQ-003

- [ ] **7.1** Tick acceptance criteria in
      `material-core/docs/requirements/REQ-003.md`, set `Status: DONE`, fill
      `Completed` and `Verified by` (e.g. "PR check + manual dispatch +
      sham-project test 2026-04-??").
- [ ] **7.2** Update `REQUIREMENTS_INDEX.md` to match.
- [ ] **7.3** REQ-004 is now unblocked — `matctl course add` has a manifest
      to patch.

---

## Open questions deferred to REQ-004 / REQ-005

- Exact YAML round-trip strategy for `matctl course add` patching
  `projects.yml` (comment preservation, key ordering). `ruamel.yaml` is the
  obvious choice but is a REQ-004 decision.
- Whether the `doc` render/deploy branch should be exercised by a real project
  before REQ-003 is marked DONE, or left as "implemented but untested until
  REQ-005 lands". Current stance: implement it, leave it untested — the first
  `doc` project in REQ-005 is the integration test.
- Whether `projects.yml` eventually grows per-project overrides (custom render
  command, extra deploy paths, access-gate flag). Out of scope here; the
  schema is deliberately minimal so REQ-004/005 can extend it without a
  migration.
