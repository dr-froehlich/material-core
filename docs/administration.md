# Administration Manual
# material.professorfroehlich.de

Operations reference for the Vorlesungen publishing pipeline. Authoring
conventions live in [`CLAUDE.md`](../CLAUDE.md); the original build-out is
documented in [`plans/deployment-pipeline.md`](plans/deployment-pipeline.md).

---

## 1. Executive Summary

Lecture scripts and slides for all THD courses live in this monorepo as Quarto
projects. Pushing to `main` triggers GitHub Actions, which renders the changed
courses (HTML book + Typst PDF + RevealJS slides) and deploys them via
`sshpass`+`scp` to Netcup webhosting under
`material.professorfroehlich.de/<name>/` (or `…/<group>/<name>/` for projects
that declare a `group` in the manifest — see §5.1). A Cloudflare Worker sits in
front of the subdomain and gates every request against access tokens stored in
a Workers KV namespace. Students receive a tokenised link via iLearn; the Worker
exchanges the token for a year-long signed session cookie on first visit.

---

## 2. Architecture Overview

```mermaid
flowchart LR
    Dev[Local repo<br/>WSL2]
    GH[GitHub<br/>main branch]
    GA[GitHub Actions<br/>publish.yml]
    NC[Netcup webhosting<br/>httpdocs/]
    CF[Cloudflare Worker<br/>+ KV: LECTURE_TOKENS]
    Stud[Student browser]
    Mgmt[matctl token<br/>local CLI]

    Dev -- git push --> GH
    GH -- triggers --> GA
    GA -- sshpass+scp --> NC
    Stud -- HTTPS --> CF
    CF -- proxy if authorized --> NC
    Mgmt -- Cloudflare API --> CF
```

| System | Role |
|---|---|
| **GitHub repo** | Source of truth: course content, Worker source, workflow, scripts |
| **GitHub Actions** | Detects changed courses (`dorny/paths-filter`), renders Quarto, deploys via SSH |
| **Netcup webhosting** | Static origin for `material.professorfroehlich.de`. No rsync in chroot — `scp` only |
| **Cloudflare DNS + Worker** | Proxies the subdomain, enforces token auth, serves the 403 page |
| **Cloudflare KV (`LECTURE_TOKENS`)** | Per-token records: `{course, label, issued, expires}` |
| **`matctl token`** | Local admin CLI that talks to the Cloudflare API to create/list/revoke tokens |

---

## 3. Data Flow

### 3.1 Publish flow (push → live)

```mermaid
sequenceDiagram
    participant Dev as Local repo
    participant GH as GitHub
    participant GA as GitHub Actions
    participant NC as Netcup

    Dev->>GH: git push origin main
    GH->>GA: trigger publish.yml
    GA->>GA: paths-filter detects changed courses
    GA->>GA: quarto render <course> (HTML + PDF)
    GA->>GA: quarto render <course>/slides
    GA->>NC: ssh mkdir + rm -rf <course>/
    GA->>NC: scp _output/book/* and slides/_output/*
    Note over NC: Live at material.professorfroehlich.de/<course>/
```

### 3.2 Access flow (student request)

```mermaid
stateDiagram-v2
    [*] --> CheckCookie
    CheckCookie --> Pass: valid signed cookie
    CheckCookie --> CheckToken: no/invalid cookie
    CheckToken --> KVLookup: ?token=... present
    CheckToken --> Forbidden: no token
    KVLookup --> SetCookie: token valid + course matches
    KVLookup --> Forbidden: missing/expired/wrong course
    SetCookie --> Redirect: 302 to clean URL
    Redirect --> Pass
    Pass --> [*]: proxy to Netcup origin
    Forbidden --> [*]: 403 page
```

The cookie is `mat_session = <scope>.<expiry>.<HMAC-SHA256>` signed with
`COOKIE_SECRET`, where `<scope>` is the token's `course` field stored verbatim.
Authorization passes when the request path starts with `/<scope>/` (or equals
`/<scope>`). Validity: 1 year. A `course="*"` token grants access to
everything. The KV field name remains `course` for backwards compatibility
even though it semantically represents a URL-path scope of arbitrary depth.

---

## 4. Scripts and Settings per System

### GitHub repository

| Item | Location | Purpose |
|---|---|---|
| Workflow | `.github/workflows/publish.yml` | Build + deploy per course |
| New course bootstrap | `new-course.sh` | Scaffolds a course directory |
| Token CLI | `matctl token` | Issue / list / revoke / show tokens |
| Worker source | `cloudflare/worker.js` | Authoritative copy; deploy manually |

**GitHub Actions secrets** (Repo Settings → Secrets and variables → Actions):

| Secret | Used by |
|---|---|
| `SSH_HOST` | Deploy step (Netcup hostname) |
| `SSH_USER` | Deploy step (Netcup SSH user) |
| `SSH_PASSWORD` | Deploy step (`sshpass -e`) |

### Cloudflare

| Item | Where | Notes |
|---|---|---|
| DNS | DNS tab | `material` A record → Netcup IP, **proxied (orange cloud)** |
| Worker | Workers & Pages → `<worker name>` | Source pasted from `cloudflare/worker.js` |
| Worker route | Worker → Triggers | `material.professorfroehlich.de/*` |
| KV namespace | Workers & Pages → KV | `LECTURE_TOKENS` |
| KV binding | Worker → Settings → Variables | `LECTURE_TOKENS` → namespace ID |
| Worker variable | Worker → Settings → Variables | `COOKIE_SECRET` (32-hex, secret) |

**Re-deploying the Worker:** edit `cloudflare/worker.js` locally, commit, then
paste into the Cloudflare dashboard editor and click *Deploy*. There is no
`wrangler.toml` — this is intentional, manual deploys are infrequent.

### Netcup

| Item | Path / setting |
|---|---|
| Subdomain | `material.professorfroehlich.de` (created in CCP → Subdomains) |
| Webroot | `/material.professorfroehlich.de/httpdocs/` |
| Per-project tree | `httpdocs/<name>/` (or `httpdocs/<group>/<name>/` when grouped — book HTML, PDF, `slides/` for courses) |
| Access | Same SSH credentials as `pfhome`; `scp` only (no rsync) |

### Local admin machine

| Item | Path |
|---|---|
| Token CLI | `matctl token` |
| Credentials | `scripts/.env` (gitignored) |

---

## 5. Configuration Files

| File | Purpose | Touch when… |
|---|---|---|
| `_brand.yml` | Repo-wide Quarto branding (colors, fonts, logo) | THD CI changes |
| `shared/base.scss` | HTML theme overrides | Visual tweaks across all courses |
| `<course>/_quarto.yml` | Course title, language, PDF `output-file` | Each new course |
| `<course>/slides/_quarto.yml` | Slide footer | Each new course |
| `projects.yml` | Manifest of publishable projects (name + type) | Each new course or doc (see §6) |
| `.github/workflows/publish.yml` | Build + deploy workflow | Tooling changes only — never per-course |
| `material_core/scripts/.env` | `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `CF_KV_NAMESPACE_ID` | Rotating Cloudflare API token (read by `matctl token`) |
| `cloudflare/worker.js` | Auth Worker source | Worker logic changes (then redeploy) |

### 5.1 Manifest: `projects.yml`

Every publishable project — course or standalone document — is enumerated in
`material/projects.yml`, alongside the groups that scope them. The CI workflow
reads it once per run and uses it for both change detection and matrix expansion.

Schema:

```yaml
projects:
  - name: <group-name>       # group entry — no directory created
    type: group
    title: "Human-Readable Group Title"

  - name: <directory-name>   # course or doc entry
    type: course | doc
    title: "Human-Readable Title"
    group: <optional>        # optional: URL-path group; project deploys under <group>/<name>/
```

Field reference:

| Field | Required on | Purpose |
|---|---|---|
| `name` | all types | Unique slug across all entries. For courses/docs: directory name in the repo and last URL path segment. For groups: URL-path prefix only (no directory). Must match `[a-z0-9][a-z0-9._-]*`. |
| `type` | all types | `group`, `course`, or `doc` — selects entry semantics and render/deploy rules. |
| `title` | all types | Human-readable title. Written by `matctl add`; defaults to title-cased slug when `--title` is omitted (course/doc only). Required for groups. |
| `group` | course, doc | Shared URL-path scope. When set, the deploy target is `httpdocs/<group>/<name>/` and the public URL becomes `material.professorfroehlich.de/<group>/<name>/`. Must match `[a-z0-9][a-z0-9._-]*`. |

**Single namespace:** `name` values are unique across all entry types — a group, a
course, and a doc cannot share a `name`. `matctl add` rejects collisions.

Worked example — a group with two member projects plus one ungrouped doc:

```yaml
projects:
  - name: mk4-26
    type: group
    title: "Mikrocomputertechnik 4 — WS 2026"
  - name: digital-und-mikrocomputertechnik
    type: course
    title: "Digital- und Mikrocomputertechnik"
    group: mk4-26            # → /mk4-26/digital-und-mikrocomputertechnik/
  - name: esp-survival-guide
    type: doc
    title: "ESP32 Survival Guide"
    group: mk4-26            # → /mk4-26/esp-survival-guide/
  - name: unrelated-standalone-doc
    type: doc
    title: "Unrelated Standalone Doc"
                             # → /unrelated-standalone-doc/
```

### 5.3 Groups

Groups scope one or more course/doc entries under a shared URL-path prefix and
allow a single token to cover all member projects (§8.1).

**Create a group before adding members:**

```bash
matctl group add <name> --title "Human-Readable Title"
```

No directory is created; only a `type: group` entry is written to `projects.yml`.

**Remove a group:**

```bash
matctl group remove <name> [--yes]
```

Fails if any course or doc entry still references the group. Remove or re-group
dependents first.

**Modify a group's title:**

```bash
matctl group modify <name> --title "New Title"
```

Updates `title` in `projects.yml` and regenerates `<group>/index.html`.

#### Group landing pages

When a group has at least one child (course or doc), matctl writes a static
`<group>/index.html` listing every child project as a link. This file is a
committed artefact — `git add <group>/index.html` and push it alongside any
manifest change.

**On-disk invariant:** `<group>/` exists on disk ⟺ the group has at least one
child. matctl creates and removes the directory automatically. If the directory
contains other files (e.g. a user stash), removal is skipped with a warning.

**Regeneration triggers** — every mutating matctl command regenerates the
landing pages of all affected groups after `save_manifest`:

| Command | Groups regenerated |
|---|---|
| `course add` / `doc add` | the new entry's `group` (if any) |
| `course remove` / `doc remove` | the removed entry's `group` (if any) |
| `course modify --title` / `doc modify --title` | the entry's current `group` (if any) |
| `course modify --group X` / `doc modify --group X` | the **old** group and the **new** group |
| `group add` | the group itself (always a no-op on disk — no children yet) |
| `group modify --title` | the group itself |
| `group remove` | skipped — group entry is already gone and was empty by precondition |

**URL:** `https://material.professorfroehlich.de/<group>/` serves the landing
page. A group-scoped token (issued as `matctl token issue <group> "..."`)
covers the landing page and every child project under it with a single cookie.

**CI deploy:** the `landing` job in `publish.yml` deploys `<group>/index.html`
to `httpdocs/<group>/index.html` after the `build` job completes. It uses the
committed file — no generation occurs in CI. If no group has a committed
`index.html`, the job is a no-op.

Render and deploy rules by type:

| `type` | Render | Deploy |
|---|---|---|
| `course` | `quarto render <name>` + `quarto render <name>/slides` | `<name>/_output/book/*` → webroot; `<name>/slides/_output/*` → `<webroot>/slides/` |
| `doc`    | `quarto render <name>` | `<name>/_output/*` → webroot |

Where `webroot` resolves to `httpdocs/<group>/<name>/` when the project has a
`group`, otherwise `httpdocs/<name>/`. Grouping is deploy-time only — Quarto
still renders into `<name>/_output/...` as if ungrouped.

Change detection: the workflow diffs the push against its base. A project is
rebuilt only when at least one changed file lives under `<name>/`. Changes to
`projects.yml` or `.github/workflows/publish.yml` rebuild everything, as does
`workflow_dispatch` and any push with no valid base commit (first push, force
push). An unrelated edit (top-level README, docs, etc.) builds nothing — the
`build` matrix is guarded by `if: needs.changes.outputs.projects != '[]'`.

`matctl course add` and `matctl doc add` patch this file automatically.

### 5.2 Project types: course vs. doc

| Type | Structure | Render | Deploy |
|------|-----------|--------|--------|
| `course` | Multi-chapter Quarto book + RevealJS slides sub-project | `quarto render <name>` + `quarto render <name>/slides` | `<name>/_output/book/*` → webroot; `<name>/slides/_output/*` → `<webroot>/slides/` |
| `doc` | Single `index.qmd`, flat `assets/` | `quarto render <name>` only | `<name>/_output/*` → webroot (no `book/` infix) |

Choose **`course`** when the project has multiple chapters, a book-level TOC,
and accompanying slides. Choose **`doc`** for single-file or small flat
publications — technical guides, reference documents, one-off write-ups — that
don't need slides or chapter navigation.

---

## 6. Course Lifecycle

Replace `<course>` with the kebab-case course slug throughout.

### 6.1 Adding a course

Run from inside the `material` checkout:

```bash
matctl course add <course> --title "Human Readable Title"
```

`matctl course add` does three things in order:

1. Copies `material_core/templates/course/` → `./<course>/`, substituting the
   declared `{{COURSE_NAME}}`, `{{COURSE_TITLE}}`, and `{{COURSE_SUBTITLE}}`
   tokens throughout the tree.
2. Appends `{name: <course>, type: course}` to `projects.yml` using
   `ruamel.yaml` in round-trip mode, so any hand-added comments or ordering
   survive. The manifest schema is described in §5.1.
3. Prints next-step hints (preview, commit, push).

No other files need editing — `.github/workflows/publish.yml` reads
`projects.yml` at CI time and fans out a `build` matrix over every registered
project automatically.

Optional flags:

| Flag | Default | Purpose |
|---|---|---|
| `--title "..."` | `<course>` title-cased | Sets the book title and slide footer |
| `--subtitle "..."` | empty | Sets the book subtitle; empty = no subtitle shown |

### 6.2 Removing a course

```bash
matctl course remove <course>          # prompts for confirmation
matctl course remove <course> --yes    # no prompt, for scripting
```

`course remove` removes the manifest entry from `projects.yml` and deletes
`./<course>/` from disk.

**What it does NOT touch** — you must handle these manually:

- Remote content at `material.professorfroehlich.de/<course>/` — delete via
  SSH or let it become a dead link.
- Cloudflare Worker KV tokens issued against the removed course — they become
  dead keys. Revoke them with `matctl token revoke <token>` (§8.3) if you want
  to clean up KV.

### 6.3 Modifying a course

```bash
matctl course modify <course> --title "New Title"
matctl course modify <course> --group <group>
matctl course modify <course> --group ""          # remove grouping (root-level deploy)
```

At least one of `--title` / `--group` must be supplied; omitting both is a
usage error (exit code 2).

`--title` updates the `title` field in `projects.yml`, `<course>/_quarto.yml`
(`book.title`), and leaves `<course>/index.qmd` unchanged (that file's
`title: "Welcome"` is a per-page heading, not the course title).

`--group` updates the `group` field in the manifest. Pass an empty string
(`--group ""`) to remove grouping — the project will then deploy at root level
on next CI run. **Changing or removing the group does not move remote content.**
A stale-path warning is printed; clean up the old deploy path manually via SSH.

### 6.4 First publish after adding a course

```bash
git add <course>/ projects.yml
git commit -m "Add course: <course>"
git push
```

Watch the run under GitHub → Actions. On success the course is live at
`https://material.professorfroehlich.de/<course>/` — but locked behind the
Worker until a token is issued (§8).

---

## 7. Document Lifecycle

Replace `<name>` with the kebab-case document slug throughout.

### 7.1 Adding a document

Run from inside the `material` checkout:

```bash
matctl doc add <name> --title "Human Readable Title"
```

`matctl doc add` does three things in order:

1. Copies `material_core/templates/doc/` → `./<name>/`, substituting the
   declared `{{DOC_NAME}}` and `{{DOC_TITLE}}` tokens throughout the tree.
2. Appends `{name: <name>, type: doc}` to `projects.yml` using `ruamel.yaml`
   in round-trip mode.
3. Prints next-step hints (preview, commit, push).

Optional flags:

| Flag | Default | Purpose |
|---|---|---|
| `--title "..."` | `<name>` title-cased | Sets the document title |

### 7.2 Removing a document

```bash
matctl doc remove <name>          # prompts for confirmation
matctl doc remove <name> --yes    # no prompt, for scripting
```

`doc remove` removes the manifest entry from `projects.yml` and deletes
`./<name>/` from disk. Remote content must be cleaned up manually (same
caveats as §6.2).

### 7.3 Modifying a document

```bash
matctl doc modify <name> --title "New Title"
matctl doc modify <name> --group <group>
matctl doc modify <name> --group ""              # remove grouping
```

`--title` updates `title` in `projects.yml` and rewrites the `title:` key in
`<name>/index.qmd` front matter. The document body and all other front-matter
keys are preserved.

`--group` behaviour is identical to `matctl course modify --group` (§6.3).

### 7.4 First publish after adding a document

```bash
git add <name>/ projects.yml
git commit -m "Add doc: <name>"
git push
```

Watch the run under GitHub → Actions. The `build` matrix resolves
`PROJECT_TYPE=doc`, runs `quarto render <name>` (no slides step), and
deploys `<name>/_output/*` flat to the webroot.

---

## 8. Token Management

All commands read credentials from `material_core/scripts/.env` inside the
package (env vars `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `CF_KV_NAMESPACE_ID`).
Process environment variables take precedence if set.

### 8.1 Issue a token

```bash
matctl token issue <course> "<label>" [--days 365]
```

Examples:

```bash
matctl token issue digital-und-mikrocomputertechnik "WS2025/26" --days 365
matctl token issue "*" "Alle Kurse WS2025/26" --days 365
```

`matctl token issue` prints the token and the ready-to-paste iLearn URL:

```
https://material.professorfroehlich.de/<course>/?token=<TOKEN>
```

Paste that link into the iLearn course. Students who follow it once receive a
1-year session cookie and can bookmark the clean URL.

**Scoped tokens — grouped projects.** The `<course>` argument is treated as a
URL-path scope by the Worker; the authorization rule is "request path starts
with `/<scope>/`, or equals `/<scope>`." This gives three useful granularities:

```bash
# Group-wide — covers every project deployed under httpdocs/mk4-26/
matctl token issue mk4-26 "WS2026 Gesamtgruppe"
# → https://material.professorfroehlich.de/mk4-26/?token=...

# Single project inside a group — covers only that subtree
matctl token issue mk4-26/esp-survival-guide "Person X"
# → https://material.professorfroehlich.de/mk4-26/esp-survival-guide/?token=...

# Ungrouped (root-level) project — unchanged from pre-group behaviour
matctl token issue digital-und-mikrocomputertechnik "WS2025/26"
# → https://material.professorfroehlich.de/digital-und-mikrocomputertechnik/?token=...
```

A student entering via the group token receives one cookie that covers every
project in the group, so cross-document links navigate without re-auth.

### 8.2 List tokens

```bash
matctl token list                  # all tokens
matctl token list <course>         # filtered
```

Expired tokens are flagged `[EXPIRED]` but remain in KV until revoked.

### 8.3 Revoke a token

```bash
matctl token revoke <token>
```

Effect is immediate — the next request to the Worker fails the KV lookup. Note
that **already-issued session cookies remain valid until they expire** (up to
1 year), because cookie verification does not consult KV. To force a global
re-auth, rotate `COOKIE_SECRET` in the Worker variables: every existing cookie
becomes invalid on next request.

### 8.4 Show token metadata

```bash
matctl token show <token>
```

Prints the raw JSON stored in KV for one token: `course`, `label`, `issued`,
`expires`.

---

## 9. Brands

### 9.1 Scope

Brand is **strictly visual**: logo, primary colour, favicon, footer text. Nothing
else. Brand-neutral assets — fonts, SCSS structure, theorems, diagram defaults —
live in `material_core/shared/` and are shared by all brands. No per-brand
templates, no per-brand language settings, no per-brand deploy paths.

### 9.2 Shipped brands

| Brand | Default? | Logo | Primary colour | Use case |
|---|---|---|---|---|
| `generic` | **yes** (new scaffolds) | none | THD blue (`#1a4273`) | Non-THD documents; neutral, no organisational marking |
| `thd` | implicit fallback for legacy entries without `brand:` | `THD-logo.png` | THD blue (`#1a4273`) | Lecture material under THD |
| `pf` | opt-in | `logo_pf.svg` | warm-gold (`#d99d44`) | Peter Fröhlich's personal documents |

### 9.3 Directory layout

```
material_core/
  brands/
    generic/
      _brand.yml        palette + footer (no logo block)
      brand.scss        SCSS variable overrides
      assets/           empty (no logo, no favicon)
    thd/
      _brand.yml
      brand.scss
      assets/
        THD-logo.png
        favicon.png
    pf/
      _brand.yml
      brand.scss
      assets/
        logo_pf.svg
        favicon.svg
  shared/               brand-neutral: base.scss, fonts, colors.tex, typst-show.typ
```

Each project directory gets four symlinks created at scaffold time (and
recreated by `matctl link`):

```
<project>/_brand.yml    → material_core/brands/<brand>/_brand.yml
<project>/brand.scss    → material_core/brands/<brand>/brand.scss
<project>/brand-assets/ → material_core/brands/<brand>/assets/
<project>/shared/       → material_core/shared/
```

`shared/` gives the project local access to brand-neutral assets (fonts,
`base.scss`, `typst-show.typ`) without relying on a repo-root symlink.
All four are listed in `.gitignore` and must never be committed — they
encode absolute paths and are regenerated by `matctl link` at CI time.

### 9.4 Using brands

Pass `--brand <name>` when scaffolding. Default is `generic`.

```bash
matctl course add my-course --lang de --brand thd   # THD lecture
matctl doc add schutzkonzept --lang de               # generic (default)
matctl doc add personal-doc --lang de --brand pf     # PF personal
```

Switch an existing project's brand:

```bash
matctl course modify my-course --brand pf
```

Rewire all per-project symlinks after a fresh checkout:

```bash
matctl link          # from the material/ repo root
matctl link --force  # force-replace existing symlinks
```

### 9.5 Brand resolution rule

- Manifest entries with `brand: <name>` use that brand.
- Legacy entries **without** a `brand:` key resolve to `thd` (backwards-compat).
- New scaffolds always write `brand:` explicitly (default: `generic`).

### 9.6 How to add a new brand

1. Create `material_core/brands/<name>/` with:
   - `_brand.yml` — palette, optional logo block, typography
   - `brand.scss` — `$brand-primary`, `$brand-secondary`, `$brand-accent`, `$brand-footer-text`
   - `assets/` — logo file(s), favicon file(s) (empty if no logo)
2. The new brand is picked up automatically by `available_brands()` at startup.
   No code change needed.
3. Bump the version in `pyproject.toml` (minor bump) and tag a release.
