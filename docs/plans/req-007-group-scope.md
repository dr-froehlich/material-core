# REQ-007 Implementation Plan — Group scope

**Goal:** Introduce the `group` concept as a shared URL-path scope covering
one or more co-deployed projects. A single token issued for a group covers
every project beneath it; the Worker is rewritten to do scope-based
path-prefix authorization; `matctl course add` / `matctl doc add` gain a
`--group` flag; CI deploys grouped projects under `httpdocs/<group>/<name>/`.

**Context:** A course and its companion documents (e.g.
`digital-und-mikrocomputertechnik` + `esp-survival-guide`) are logically
one unit with internal cross-links. Today each top-level segment needs its
own token because the Worker scopes cookies to the first URL segment.
Students who enter via one token cannot follow links into the other path
without re-authenticating. REQ-007 fixes this by letting both projects
share a URL prefix (`mk4-26/…`) that one token can cover.

**Scope boundary:** Only the pieces listed in REQ-007 §1–§7: Worker
authorization logic, CI deploy-path changes, the `--group` flag, and the
`group:` field in `projects.yml`. The `type: group` manifest entry, group
lifecycle commands (`matctl group add/remove/modify`), `modify` on
courses/docs, and title metadata are **REQ-008**. The auto-generated
`<group>/index.html` landing page is **REQ-009**.

**Status tracking:** `[ ]` open · `[~]` in progress · `[x]` done

---

## Design decisions

### D1 — `group` is an optional field on existing entries, not a new type

This requirement lands *without* introducing `type: group` manifest
entries. That deliberately keeps REQ-007 small: the CLI, Worker, and CI
only need to know "does this project have a group string?" — they never
need to resolve a group definition. REQ-008 layers on the `type: group`
entry, title metadata, and existence-validation across entries. A manifest
produced by REQ-007 is forward-compatible: REQ-008 will add the top-level
group entries; the per-project `group:` field is unchanged.

Consequence for validation in REQ-007: the `--group` value is validated
only against the slug regex `[a-z0-9][a-z0-9._-]*`. No cross-entry
consistency check (e.g. "all projects with `group: mk4-26` agree on
existence of a matching group entry") — that check belongs to REQ-008.

### D2 — KV field name stays `course`; semantics become "URL scope"

The Worker's KV records already use the field name `course`. REQ-007 keeps
that field name to avoid a KV migration, even though the value is now
better described as a URL path scope. Existing records with
`course: "digital-und-mikrocomputertechnik"` satisfy the new
prefix-matching rule unchanged. New records just store a scope string
that may contain a slash (`mk4-26/esp-survival-guide`) or be a bare group
(`mk4-26`). Code comments and docs name the concept "scope"; the wire
format keeps "course".

### D3 — Worker authorization via path-prefix match

Current rule: `record.course === course` where `course` is the first path
segment. New rule: the request pathname starts with `/<record.course>/`,
or equals `/<record.course>` exactly (edge case: bare scope URL with no
trailing slash). Wildcard `*` continues to short-circuit to true. The
prefix test is done with `pathname.startsWith(prefix + "/")` plus the
equality check — not string-prefix alone, which would let
`/mk4-26-evil/...` satisfy a `mk4-26` scope.

### D4 — Cookie stores the scope verbatim, not the first URL segment

Today `makeSessionCookie` is called with the single-segment course; the
cookie encodes that segment and `verifySessionCookie` checks equality
against the current request's first segment. After REQ-007, both
functions take a scope string and check the same prefix rule used by
`isAuthorized`. The scope written into the cookie is the token record's
`course` field at the moment of issue — not the current request path.
That way, a `mk4-26` token produces a `mk4-26` cookie that covers every
project under `/mk4-26/**`, including the one the student did not enter
through.

Legacy cookies from before this change are ignored — the site has not
been in productive use, so no migration or backwards-compatibility
handling is warranted. Any student still holding an old cookie
re-authenticates by clicking their iLearn link.

### D5 — iLearn URL derivation: one rule for the path, special-case `*`

`matctl token issue` builds the URL by:

- `*` → `{SITE_BASE}/?token=<tok>` (unchanged)
- any other value → `{SITE_BASE}/{course}/?token=<tok>` (unchanged
  source code, but the `course` value may now contain a slash)

No parsing, no splitting — the scope string is already the URL path.
`mk4-26` joins as `/mk4-26/`; `mk4-26/esp-survival-guide` joins as
`/mk4-26/esp-survival-guide/`. The existing `f"{SITE_BASE}/{course}/?token={tok}"`
line continues to work without change.

### D6 — `add_project` grows an optional `group` parameter

`_projects.add_project(doc, name, type_, group=None)`: when `group` is
not `None`, write a third key `group: <value>` into the entry after
`name` and `type`. Field order matters for readability of the rendered
YAML; `ruamel.yaml` preserves insertion order. Existing callers pass no
group and continue to produce today's two-key entries.

### D7 — Plan includes the `material` repo edits inline

`material` is the sibling repo I own and deploy from; no one else
touches it. Phase 5 lists the concrete edits to
`material/projects.yml` and `material/.github/workflows/publish.yml`
as part of this plan, not as a "separate PR in another repo." They
land together with the `material-core` tag bump.

### D8 — `matctl remove` note reads `group` from the manifest before deletion

The post-remove note currently prints
`material.professorfroehlich.de/<name>/`. After REQ-007, if the manifest
entry has a `group`, the note prints
`material.professorfroehlich.de/<group>/<name>/`. The group value is read
from the entry *before* it is removed from the manifest. If the entry is
absent (directory-only cleanup), the note falls back to the ungrouped
form — the group value is unavailable and that is acceptable.

### D9 — No manifest backfill, no migration command

There is exactly one real project today (`digital-und-mikrocomputertechnik`),
and the only reason to introduce a group is the MK4-26 cohort going live
with the `esp-survival-guide` companion doc. Phase 5 adds `group: mk4-26`
to both entries by hand as part of the REQ-007 rollout. No automated
migration is warranted.

---

## Phase 1 — Manifest schema: `group` in `_projects.py`

- [ ] **1.1** Update `add_project(doc, name, type_, group=None)` in
      `material_core/_projects.py` to accept the optional `group`
      parameter. When provided, append `entry["group"] = group` after
      `entry["type"] = type_` so the YAML renders as `name → type → group`.
- [ ] **1.2** Validate `group` against `_NAME_RE` at the CLI boundary
      (not in `_projects.py`, which is a pure data helper). The
      validation sits next to the existing `name` check in
      `_scaffold_project`.
- [ ] **1.3** No change to `remove_project` or `project_names` — both
      operate on `name` alone and continue to work regardless of
      whether the entry has a `group` key.

## Phase 2 — CLI: `--group` on `course add` / `doc add`

- [ ] **2.1** Extend `_scaffold_project` in `material_core/cli.py` to
      accept an optional `group: str | None` keyword argument. Validate
      with `_NAME_RE` when non-None (reuse the same error message shape
      as the `name` check). Pass it through to
      `add_project(manifest, name, project_type, group=group)`.
- [ ] **2.2** Add `--group` to `course_add`:
      ```python
      @click.option("--group", default=None,
                    help="Optional URL-path group; deploys under <group>/<name>/.")
      ```
      Forward to `_scaffold_project(..., group=group)`.
- [ ] **2.3** Add the identical `--group` option to `doc_add`. Forward
      the same way.
- [ ] **2.4** No change to the scaffold template itself. The `group` is
      a deploy-time concept; Quarto never sees it.
- [ ] **2.5** Update the scaffold's "next steps" echo to mention the
      grouped URL when `--group` was used. Minimal touch: only the
      `git commit` and `git push` lines need no change; the preview
      hint still uses the bare project path (`quarto preview <name>`),
      which Quarto renders identically.

## Phase 3 — `matctl course remove` / `doc remove`: grouped cleanup note

- [ ] **3.1** In `_remove_project`, before removing the manifest entry,
      read the `group` value off the entry (if present). Pass it into
      the final `click.echo` so the note reads
      `material.professorfroehlich.de/<group>/<name>/` when grouped.
      The manifest lookup uses the same loop pattern as `remove_project`.
- [ ] **3.2** Directory-only cleanup (entry already gone): fall back to
      the ungrouped URL with a parenthetical hint, e.g. "remote path
      depends on the original group, if any".

## Phase 4 — Worker: scope-based path-prefix authorization

All edits in `material_core/cloudflare/worker.js`.

- [ ] **4.1** Remove the current `course = url.pathname.split("/").filter(Boolean)[0]`
      extraction and its `if (!course) return fetch(request)` early
      return. Authorization works directly off `url.pathname`.
      Bare-root and any other unauthenticated request falls through
      to the standard 403 path — the subdomain is only meant to be
      entered via an iLearn link, so the 403 banner is the right
      response. No special cases.
- [ ] **4.2** Rewrite `isAuthorized(record, pathname)` to the spec in
      REQ-007 §3:
      ```js
      function isAuthorized(record, pathname) {
        if (record.course === "*") return true;
        const prefix = "/" + record.course;
        return pathname === prefix
            || pathname.startsWith(prefix + "/");
      }
      ```
      Rename the parameter from `course` to `pathname` at the call site.
- [ ] **4.3** Change `makeSessionCookie(scope, secret)` — rename the
      first parameter from `course` to `scope` for clarity. The body is
      unchanged; a scope string just happens to sometimes contain a
      slash now. HMAC-over-the-message still works because the message
      format is `<scope>.<expiry>` and neither `.` nor `/` breaks the
      split on `.` that `verifySessionCookie` does (the scope may
      contain `/` but not `.`).
- [ ] **4.4** Rewrite `verifySessionCookie(value, pathname, secret)` to
      (a) take the full pathname instead of the first segment, and
      (b) perform the same prefix test used by `isAuthorized` against
      `cookieScope`:
      ```js
      const [cookieScope, expiryStr] = parts;
      // ...existing expiry + HMAC verification unchanged...
      if (cookieScope !== "*") {
        const prefix = "/" + cookieScope;
        if (pathname !== prefix && !pathname.startsWith(prefix + "/")) {
          return null;
        }
      }
      return { scope: cookieScope, expiry };
      ```
- [ ] **4.5** Update the call sites in `fetch`:
      - Cookie verify: `verifySessionCookie(sessionValue, url.pathname, env.COOKIE_SECRET)`.
      - Token check: `isAuthorized(record, url.pathname)`.
      - Cookie issue: `makeSessionCookie(record.course, env.COOKIE_SECRET)`
        — pass the token's scope verbatim, not the URL's first segment.
- [ ] **4.6** `forbidden(pathname)` — the 403 page currently shows the
      first URL segment as "Kurs: `<course>`". Pass `url.pathname` and
      display it verbatim. No special parsing.
- [ ] **4.7** Cookie scope/path: the `Path=/` cookie attribute already
      makes the cookie visible site-wide, so a `mk4-26` cookie gets
      sent on `/mk4-26/other-project/` requests. No change needed.

## Phase 5 — `material` repo: manifest rollout, CI deploy path, pinned-ref bump

Diffs in `/home/peter/material/` — landed as one commit after the
`material-core` tag is cut (Phase 7).

- [ ] **5.1** In `material/projects.yml`, add `group: mk4-26` to the
      `digital-und-mikrocomputertechnik` course entry and register the
      new `esp-survival-guide` doc with `group: mk4-26`. Scaffold the
      doc via the new CLI: `matctl doc add esp-survival-guide --group mk4-26`.
      (Content authoring is out of scope for this plan.)
- [ ] **5.2** In `material/.github/workflows/publish.yml`, update the
      deploy block:
      - In the `Resolve project type` step, also resolve `GROUP`:
        ```bash
        GROUP=$(yq -r ".projects[] | select(.name == \"$PROJECT\") | .group // \"\"" projects.yml)
        if [[ -n "$GROUP" ]]; then
          DEPLOY_PATH="${GROUP}/${PROJECT}"
        else
          DEPLOY_PATH="${PROJECT}"
        fi
        echo "DEPLOY_PATH=$DEPLOY_PATH" >> "$GITHUB_ENV"
        ```
      - In `Deploy to Netcup`, replace `WEBROOT=".../httpdocs/${PROJECT}"`
        with `WEBROOT=".../httpdocs/${DEPLOY_PATH}"`. The `mkdir -p` +
        `rm -rf` line already uses `${WEBROOT}` and picks up the new
        path unchanged.
- [ ] **5.3** Bump `env.MATERIAL_CORE_REF` in the same workflow file to
      the new `material-core` tag (see Phase 7).
- [ ] **5.4** Change detection is unaffected. Source files still live
      under `<name>/` in the repo; the matrix filter still matches on
      `^${name}/`. Grouping is deploy-time only.

## Phase 6 — Documentation

- [ ] **6.1** `docs/administration.md §5.1` — extend the manifest schema
      example and table to include the optional `group` field with a
      one-line explanation ("shared URL scope under which this project
      deploys"). Add a worked example showing two entries sharing
      `group: mk4-26`.
- [ ] **6.2** `docs/administration.md §8.1` — add a paragraph on
      fully-qualified scope tokens, showing both
      `matctl token issue mk4-26 "WS2026"` and
      `matctl token issue mk4-26/esp-survival-guide "Person X"` with
      their respective iLearn URLs. Note the prefix-matching semantics.
- [ ] **6.3** `docs/administration.md §2 / §3` — update any path
      examples that assume single-segment courses (`/course/...`) to
      cover the grouped form too. Minimal edits; the architecture text
      stays otherwise accurate.
- [ ] **6.4** `material-core/CLAUDE.md` — in the `matctl CLI` block,
      add `[--group <name>]` to the `course add` / `doc add` entries
      with a one-line description. Bump the "Current status" line to
      include REQ-007 DONE. Bump the pinned version in the consumption
      examples (`v0.4.0` → next tag).

## Phase 7 — Release and close-out

- [ ] **7.1** Tick acceptance criteria in
      `docs/requirements/REQ-007.md`, set `Status: DONE`, fill
      `Completed` and `Verified by`.
- [ ] **7.2** Update `REQUIREMENTS_INDEX.md` to match.
- [ ] **7.3** Tag `material-core` `v0.5.0` (new CLI flag + Worker
      behaviour change = minor bump; no breaking CLI surface removed).
- [ ] **7.4** Commit Phase 5 in `material` (manifest + workflow + ref
      bump) against the new tag; push to `main`.
- [ ] **7.5** Redeploy the Worker. Wrangler or the dashboard — both
      paths are documented in `docs/administration.md`.

---

## Manual acceptance run (maps to REQ-007 §Acceptance criteria)

Do these in order after Phase 5 is merged and the Worker is redeployed.

- [ ] **A1** `matctl doc add esp-survival-guide --group mk4-26` writes
      `group: mk4-26` to the manifest entry.
- [ ] **A2** `matctl course add <scratch-course> --group mk4-26` writes
      `group: mk4-26` on a course entry (throwaway scratch dir; revert).
- [ ] **A3** Scaffold without `--group` — the emitted manifest entry
      is byte-identical to today's (no `group:` key).
- [ ] **A4** `matctl token issue mk4-26 "A4 smoke"` prints a URL of the
      form `.../mk4-26/?token=...`. Verify via `matctl token show`.
- [ ] **A5** `matctl token issue mk4-26/digital-und-mikrocomputertechnik
      "A5 smoke"` prints `.../mk4-26/digital-und-mikrocomputertechnik/?token=...`.
- [ ] **A6** Live browser: token from A4 grants access to both
      `/mk4-26/digital-und-mikrocomputertechnik/` and
      `/mk4-26/esp-survival-guide/`. Cross-document link navigates
      without a second auth round-trip.
- [ ] **A7** Live browser: token from A5 grants
      `/mk4-26/digital-und-mikrocomputertechnik/` but returns 403 on
      `/mk4-26/esp-survival-guide/`.
- [ ] **A8** Live browser: an existing root-level token
      (`course: "digital-und-mikrocomputertechnik"`, pre-REQ-007) still
      grants access after Worker redeploy.
- [ ] **A9** Live browser: a `course: "*"` token still grants access to
      everything after Worker redeploy.
- [ ] **A10** SSH into Netcup and confirm the deployed tree:
      `httpdocs/mk4-26/digital-und-mikrocomputertechnik/`,
      `httpdocs/mk4-26/esp-survival-guide/`, and any ungrouped project
      still at `httpdocs/<name>/`.
- [ ] **A11** Revoke the A4 and A5 smoke tokens via `matctl token revoke`.

---

## Commit strategy

`material-core`:

1. **Phases 1–3** — `_projects.py` + `cli.py` `--group` flag + remove
   note. One focused Python-side commit.
2. **Phase 4** — Worker rewrite. Separate because the JS diff stands on
   its own and is the risky change.
3. **Phase 6** — documentation. Separate so doc-only review stays light.
4. **Phase 7** — REQ status + index + version bump + tag.

`material` (one commit, after `material-core` is tagged):

1. **Phase 5** — manifest edits + `publish.yml` deploy-path + pinned
   ref bump. Single commit that lands the end-to-end grouped deploy.

## Risks and mitigations

- **Pathname prefix test admits sibling-directory spoofing.** The
  `pathname.startsWith(prefix + "/")` test prevents `/mk4-26-evil/*`
  from matching scope `mk4-26`. The equality check covers the
  `/<scope>` bare-scope case. Unit-level verification belongs to
  Phase 4 smoke tests if any JS test harness exists — today the
  Worker has none, so A6/A7 live-browser checks are the only gate.
- **`yq` reading `.group // ""` silently on old manifests.** `yq -r
  '... // ""'` returns an empty string for missing fields, so the CI
  step degrades cleanly on ungrouped projects. Verified by keeping at
  least one ungrouped project in the Phase 5 rollout and building it.
- **Scope string containing `.` breaks cookie parsing.** The cookie
  format is `<scope>.<expiry>.<hmac>` and the verifier splits on `.`
  (via `parts.pop()` for the sig and `parts.join(".")` for the
  message, which is safe) then treats `parts[0]` as the scope. A
  scope with a literal `.` would land in `parts[0]` but `parts[1]`
  would become an unexpected segment — breakage. The slug regex
  `[a-z0-9][a-z0-9._-]*` does allow `.`, but existing project names
  don't use it and group names shouldn't either. Add a runtime check
  in `makeSessionCookie` that throws on `scope.includes(".")` — fail
  loudly if a future group name contains a dot, rather than issuing
  a corrupt cookie. Alternative: URL-encode the scope in the cookie.
  The throw is simpler; revisit if `.` in slugs is ever intentional.
- **Change-detection matrix misses grouped-project edits.** Source
  still lives under `<name>/`, so the existing `^${name}/` filter
  matches. A grouped project rebuilds iff its own files change —
  correct. A "touch every sibling when one changes" rebuild is not
  desired.

## Explicitly out of scope (deferred or covered elsewhere)

- `type: group` manifest entries, group titles, `matctl group
  add/remove/modify`, `matctl course/doc modify` → **REQ-008**.
- Auto-generated `<group>/index.html` landing page → **REQ-009**.
- Content-level cross-link conventions (absolute vs. relative) —
  guidance only, no tooling. Authoring reference will cover this
  separately if needed.
- Worker test harness — no JS tests today; adding one is its own
  requirement.
- Token bulk ops scoped to a group (`matctl token revoke --group X`)
  — not in REQ-006, not in REQ-007.
- KV field rename from `course` to `scope` — deliberately deferred
  (D2). A future requirement can do a backwards-compatible rename if
  the cognitive cost of the misnamed field outweighs the migration
  cost.
