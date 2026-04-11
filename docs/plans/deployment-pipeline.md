# Deployment Pipeline Plan
# material.professorfroehlich.de

**Goal:** Automatic build + deploy of lecture scripts (HTML + PDF) and slides to
`material.professorfroehlich.de` on push to `main`, with per-course token-gated access
validated by a Cloudflare Worker.

**Status tracking:** Each task is marked `[ ]` open, `[x]` done, `[~]` in progress.

---

## Phase 1 — DNS & Hosting Infrastructure  *(Your actions)*

- [x] **1.1 Move professorfroehlich.de to Cloudflare DNS**
  - Create free Cloudflare account (or log in if existing)
  - Add site `professorfroehlich.de` → Cloudflare imports existing DNS records automatically
  - At Netcup CCP: change nameservers to Cloudflare's (shown after import)
  - Verify all existing records are intact (A, MX, any redirects)
  - The existing A record for `professorfroehlich.de → peterfroehlich.de IP` stays as-is

- [x] **1.2 Add `material` subdomain**
  - Cloudflare DNS → Add A record: `material` → same IP as your Netcup webhosting
  - **Enable Cloudflare proxy** (orange cloud icon) — required for Worker to intercept requests

- [x] **1.3 Create Netcup webroot for subdomain**
  - Netcup CCP → Hosting → Subdomains → Add `material.professorfroehlich.de`
  - Note the webroot path (expected: `/material.professorfroehlich.de/httpdocs`) -> yes, the path is confirmed.
  - Confirm SSH/SCP access works to that path (same credentials as pfhome)

- [x] **1.4 Create Cloudflare KV namespace**
  - Cloudflare Dashboard → Workers & Pages → KV → Create namespace: `LECTURE_TOKENS`
  - Note the namespace ID (needed when deploying the Worker)

- [x] **1.5 Deploy Cloudflare Worker** *(Claude provides the script)*
  - Workers & Pages → Create Worker → paste script provided by Claude
  - Settings → Variables → Add: `COOKIE_SECRET` = random 32-char string (use
    `openssl rand -hex 16` to generate)
  - Settings → KV Namespace Bindings → bind `LECTURE_TOKENS` to the Worker
  - Settings → Triggers → Add route: `material.professorfroehlich.de/*`

- [x] **1.6 Add GitHub Secrets**
  - Repo Settings → Secrets and variables → Actions → add:
    - `SSH_HOST` — Netcup webhosting hostname
    - `SSH_USER` — SSH username
    - `SSH_PASSWORD` — SSH password
  - (Same values as pfhome — reuse if both repos are under the same GitHub account)

---

## Phase 2 — GitHub Actions  *(Claude's work)*

- [x] **2.1 Commit fonts to repo**
  - Add `shared/assets/fonts/` with the five font files from `/usr/local/share/fonts/`
    (Saira variable + italic, Daniel Regular/Bold/Black)
  - Update `_brand.yml` font source from `system` to `file` with paths
  - These are free-licensed fonts; committing them to the repo is fine

- [x] **2.2 Rewrite `publish.yml`**
  - Switch deployment from rsync+SSH-key to `sshpass`+`scp` (Netcup has no rsync in
    chroot — confirmed by pfhome experience)
  - Drop `tinytex: true` — we use Typst via orange-book, not LaTeX; Quarto 1.10+ bundles
    Typst automatically
  - Add font installation step (copy from `shared/assets/fonts/` to `~/.local/share/fonts/`)
  - Use `dorny/paths-filter` for per-course path filtering (replaces the fragile
    `contains(github.event.head_commit.modified, ...)` approach)
  - Remove the placeholder `electrical-drives` job (no such course exists)
  - Render both `--to html` and `--to orange-book-typst`; deploy both

- [x] **2.3 Define deployment layout on Netcup**
  ```
  /material.professorfroehlich.de/httpdocs/
  └── digital-und-mikrocomputertechnik/
      ├── index.html          (book HTML entry point)
      ├── esp-survival-guide/ (individual chapter pages)
      ├── digital-und-mikrocomputertechnik.pdf
      └── slides/
          └── ...
  ```
  Each course push deploys only that course's subtree (other courses untouched).

---

## Phase 3 — Token System  *(Claude's work)*

### Architecture

```
Student browser
  → https://material.professorfroehlich.de/digital-und-mikrocomputertechnik/?token=abc123
  → Cloudflare Worker (runs on every request to material.*)
      → Check for valid signed cookie  (fast path, return visitors)
      → No cookie: check ?token= query param → KV lookup
          → Valid token for this course: set cookie, redirect (strips token from URL)
          → Invalid/expired/wrong course: serve 403 page
  → If authenticated: proxy request transparently to Netcup origin
```

### KV Record Schema

```
Key:   "tok:<token-string>"
Value: {
  "course": "digital-und-mikrocomputertechnik",   // or "*" for all-courses
  "label":  "WS2025/26",
  "issued": "2025-09-01",
  "expires": "2026-09-30"
}
```

### Token Lifecycle

- Issued once per cohort per course at semester start (e.g. start of WS, start of SS)
- Default lifetime: 12 months → covers current semester + one retry semester
- Rotation: issue new token for new cohort; old token expires naturally (no forced revocation)
- Emergency revocation: delete KV key (immediate effect, no deploy needed)
- Token is delivered to students via the Moodle course link — changing Moodle link = new token

### Cloudflare Worker — Key Behaviors

- [x] **3.1 Write Worker script**
  - Cookie check first (no KV read needed for return visitors)
  - `?token=` → KV lookup → verify course matches requested path prefix
  - Valid: set `HttpOnly; Secure; SameSite=Lax; Max-Age=31536000` cookie, 302 redirect
    to same URL without `?token=` param (clean bookmark URL)
  - Invalid/missing: serve styled 403 page (no redirect, no leaking of valid paths)
  - Assets (CSS/JS/images/fonts): pass through if cookie is valid — no extra KV reads

- [x] **3.2 Write `scripts/manage-tokens.sh`**
  - Commands: `issue`, `list`, `revoke`
  - Uses Cloudflare API (needs `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `CF_KV_NAMESPACE_ID`)
  - Example:
    ```bash
    ./scripts/manage-tokens.sh issue digital-und-mikrocomputertechnik "WS2025/26" 365
    # → prints the token to use in the Moodle link
    ```

---

## Phase 4 — First Real Course  *(Joint)*

- [x] **4.1 Create course** *(Your action)*
  ```bash
  ./new-course.sh digital-und-mikrocomputertechnik
  ```

- [x] **4.2 Create first document** *(Your action)*
  - Add `digital-und-mikrocomputertechnik/chapters/esp-survival-guide.qmd`
  - Small but real content — enough to test the full pipeline

- [x] **4.3 Add course to workflow** *(Claude's action)*
  - Add the `digital-und-mikrocomputertechnik` job block to `publish.yml`

- [x] **4.4 End-to-end test** *(Joint)*
  - Push to `main`
  - Verify GitHub Actions build succeeds (HTML + PDF)
  - Verify files appear on Netcup at correct path
  - Issue a test token via `manage-tokens.sh`
  - Test token URL in browser → verify redirect + cookie → verify content loads
  - Test expired/invalid token → verify 403

---

## Open Questions / Notes

- **Daniel font usage:** Wired in `_brand.yml` but where Quarto applies it (headings vs body)
  depends on orange-book's typography defaults. Check PDF output once the first course renders.
- **Slides access control:** Slides are under the same subdomain, so the Worker covers them too.
  Same token grants access to both book and slides for a course.
- **Public resources:** The plan is extensible — a token with `"course": "*"` or a special
  public path prefix (e.g. `/public/`) that the Worker always allows through.
- **Netcup rsync:** Not available in chroot environment; using sshpass+scp (same as pfhome).
- **Quarto PDF vs HTML render:** Two separate `quarto render` calls in the workflow;
  the Typst/orange-book render does not produce HTML and vice versa.
