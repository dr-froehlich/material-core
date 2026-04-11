# REQ-006 Implementation Plan — `matctl token` lifecycle CLI

**Goal:** Port `material_core/scripts/manage-tokens.sh` to a Python
`matctl token {issue,list,revoke,show}` command group, adding `httpx` as
the only new dependency. KV schema unchanged — existing tokens keep
working.

**Context:** REQ-001 split tooling out of `material`; REQ-004 established
`matctl` as the real home for admin operations (not a shell grab-bag in
`scripts/`). The token-management shell script is the last piece of admin
tooling still living outside `matctl`. REQ-006 folds it in so there is
exactly one CLI surface for course and token lifecycle, and so the
`.env`-driven credential dance stops being special.

**Scope boundary:** No Worker changes. No KV schema changes. No new
token semantics (validity, rotation, bulk ops) — this is a direct port.

**Status tracking:** `[ ]` open · `[~]` in progress · `[x]` done

---

## Design decisions

### D1 — `httpx` sync, not `requests` or stdlib

`httpx>=0.27` is modern, maintained, and has a clean sync API. Four admin
calls per invocation — no async needed. One new dep, small surface. Pinned
loosely (`>=0.27,<0.29`) — 0.27/0.28 are stable; widen when 0.29 ships and
proves itself.

### D2 — New private module `_cloudflare.py`

Keep KV plumbing out of `cli.py`. Expose a thin `KVClient` class
(constructor takes the three credentials; methods `put/get/delete/
list_keys`). REQ-006 is the only caller today, but isolating HTTP from
Click command bodies keeps `cli.py` readable and makes the
credential-loading logic testable by hand.

### D3 — Credential loading: env first, then `scripts/.env`, then clear error

Same precedence as the shell script. `.env` lookup uses
`importlib.resources.files("material_core") / "scripts" / ".env"` so it
works under both editable and pinned pipx installs. Parse with a tiny
hand-rolled `KEY=value` loop — adding `python-dotenv` for ~10 lines of
parsing is overkill. Missing variables raise `ClickException` naming the
exact var, not a traceback.

### D4 — Token generation: `secrets.token_hex(12)`

24 lowercase hex chars. The shell script's alphabet is `[a-z0-9]`; hex is
a strict subset, so all list/show/revoke operations remain compatible
with tokens already in KV. Tokens are opaque keys — nothing decodes them.

### D5 — Date handling: `datetime.date` + `timedelta`

Both `issued` and `expires` stored as `YYYY-MM-DD` strings to match the
existing KV schema exactly. Expiry comparison in `list` uses
`date.fromisoformat` — trivially cross-platform, unlike the shell script's
`date -d` / `date -jf` dance.

### D6 — `list` pretty-printing: computed column widths

Keep the shell script's fixed-width table (`TOKEN | COURSE | LABEL |
ISSUED | EXPIRES`) but compute column widths from the data rather than
hard-coding 26/45/20/12/12. One pass to collect rows, one pass to print.
Expired rows get `[EXPIRED]` appended to the EXPIRES cell, same as the
shell script.

### D7 — `show` returns raw KV JSON, pretty-printed

`json.dumps(raw, indent=2)`. Not-found (HTTP 404) becomes a
`ClickException("token not found")`, not a traceback or empty output.

### D8 — Shell script stays until production verification, then deleted

Per the requirement notes: no gap in admin capability during development.
Phase 6 does the deletion only after Phase 5 acceptance passes against
real KV state.

---

## Phase 1 — Add `httpx` dependency

- [ ] **1.1** Add `"httpx>=0.27,<0.29"` to
      `pyproject.toml [project].dependencies`.
- [ ] **1.2** `pipx install --editable /home/peter/projects/material-core`
      to pick up the new dep. Confirm `python -c "import httpx; print(
      httpx.__version__)"` inside the pipx venv.
- [ ] **1.3** No commit yet — folds into Phase 3 so `main` never carries
      an unused dependency.

## Phase 2 — Implement `material_core/_cloudflare.py`

- [ ] **2.1** Create the module with:
  - `load_credentials() -> tuple[str, str, str]` — env → `scripts/.env`
    → `ClickException`. Returns `(account_id, api_token, namespace_id)`.
    Error message names the exact variable that is missing.
  - `_parse_env_file(path: Path) -> dict[str, str]` — simple `KEY=value`
    parser. Strips surrounding single/double quotes, skips blank lines
    and `#` comments, ignores malformed lines. No shell interpolation.
  - `KVClient` class — constructor stores the three credentials and
    builds the base URL
    `https://api.cloudflare.com/client/v4/accounts/{account}/storage/kv/namespaces/{ns}`.
    Implements `__enter__` / `__exit__` so callers use it in a `with`
    block; opens an `httpx.Client(timeout=10.0)` with the
    `Authorization: Bearer ...` header set once.
  - Methods:
    - `put(key: str, value: dict) -> None` — `PUT
      /values/{encoded-key}` with `Content-Type: application/json`,
      body is `json.dumps(value)`. Raises on non-2xx.
    - `get(key: str) -> dict | None` — `GET /values/{encoded-key}`.
      Returns `None` on 404, parsed JSON otherwise, raises on other
      errors.
    - `delete(key: str) -> bool` — `DELETE /values/{encoded-key}`.
      `True` if deleted, `False` on 404, raises on other errors.
    - `list_keys(prefix: str) -> list[str]` — `GET
      /keys?prefix={encoded-prefix}&limit=1000`, returns
      `[item["name"] for item in response["result"]]`.
  - Key encoding: `urllib.parse.quote(key, safe="")` so `tok:<token>`
    becomes `tok%3A<token>`, matching the shell script.
- [ ] **2.2** No formal tests — consistent with REQ-004. Coverage comes
      from the Phase 4 manual acceptance run against real KV.

## Phase 3 — Wire `matctl token` group in `cli.py`

- [ ] **3.1** Add `@main.group() def token(): "Manage lecture access
      tokens."` alongside the existing `course` group.
- [ ] **3.2** `token issue`:
  ```python
  @token.command("issue")
  @click.argument("course")
  @click.argument("label")
  @click.option("--days", type=int, default=365,
                help="Validity period in days (default: 365).")
  def token_issue(course: str, label: str, days: int) -> None: ...
  ```
  Flow:
  1. `account, api_token, ns = load_credentials()`.
  2. `token = secrets.token_hex(12)`.
  3. `issued = date.today().isoformat()`;
     `expires = (date.today() + timedelta(days=days)).isoformat()`.
  4. `with KVClient(...) as kv: kv.put(f"tok:{token}", {"course":
     course, "label": label, "issued": issued, "expires": expires})`.
  5. Print summary block: Token / Course / Label / Issued / Expires
     (with `(N days)` suffix).
  6. Print iLearn URL. If `course == "*"`:
     `https://material.professorfroehlich.de/?token=<token>`, else
     `https://material.professorfroehlich.de/<course>/?token=<token>`.
- [ ] **3.3** `token list`:
  ```python
  @token.command("list")
  @click.argument("course", required=False)
  def token_list(course: str | None) -> None: ...
  ```
  Flow:
  1. Load creds; open `KVClient`.
  2. `keys = kv.list_keys("tok:")`; strip the `tok:` prefix.
  3. If empty: `click.echo("No tokens found."); return`.
  4. For each key, `raw = kv.get(f"tok:{tok}") or {}` — tolerate
     individual fetch failures the same way the shell script does
     (empty dict → blank cells).
  5. Filter by `course` if given (compare against `raw.get("course")`).
  6. Expiry check: `date.fromisoformat(raw["expires"]) < date.today()`
     → append ` [EXPIRED]` to the expires cell. Guard the parse with
     `try/except ValueError` so a malformed date doesn't crash the
     listing.
  7. Compute column widths (`max(len(header), max(len(row[i]) for row
     in rows))`) and print with an f-string format spec. Header row +
     separator row of dashes + data rows.
- [ ] **3.4** `token revoke`:
  ```python
  @token.command("revoke")
  @click.argument("token_value")
  def token_revoke(token_value: str) -> None: ...
  ```
  Flow:
  1. Load creds; open `KVClient`.
  2. `deleted = kv.delete(f"tok:{token_value}")`.
  3. If `deleted`: `click.echo(f"Token '{token_value}' revoked.")`;
     else: `click.echo(f"Token '{token_value}' not found (already
     revoked?).")` — non-zero exit not warranted; idempotent like the
     shell script.
  4. Help text mentions: "Session cookies remain valid until
     `COOKIE_SECRET` rotation — see administration.md §7."
- [ ] **3.5** `token show`:
  ```python
  @token.command("show")
  @click.argument("token_value")
  def token_show(token_value: str) -> None: ...
  ```
  Flow:
  1. Load creds; open `KVClient`.
  2. `raw = kv.get(f"tok:{token_value}")`.
  3. If `raw is None`: `raise ClickException("token not found")`.
  4. `click.echo(json.dumps(raw, indent=2))`.
- [ ] **3.6** Verify `matctl --help` lists exactly `link`, `unlink`,
      `course`, `token`. `matctl token --help` lists `issue`, `list`,
      `revoke`, `show`.

## Phase 4 — Manual acceptance run against real KV

Against the live KV namespace, using the real `scripts/.env`. Maps
directly to the REQ-006 acceptance criteria.

- [ ] **4.1** `matctl token issue digital-und-mikrocomputertechnik
      "REQ-006 smoke" --days 30` — returns a token + correctly formed
      iLearn URL (`/digital-und-mikrocomputertechnik/?token=...`).
      Verify via `matctl token show <token>`.
- [ ] **4.2** `matctl token issue "*" "REQ-006 all-courses smoke"
      --days 30` — URL uses bare root (`/?token=...`), not
      `/*/?token=...`.
- [ ] **4.3** `matctl token list` — table includes both tokens just
      issued, plus any pre-existing ones from the shell script era
      (cross-compat check — old-alphabet tokens must still display).
- [ ] **4.4** `matctl token list digital-und-mikrocomputertechnik` —
      filters correctly, excludes the `*` token.
- [ ] **4.5** `matctl token show <token>` on both new tokens — prints
      raw JSON with `course/label/issued/expires` fields, pretty-printed.
- [ ] **4.6** `matctl token revoke <token>` for both new tokens —
      subsequent `token show` raises "token not found"; `token list` no
      longer includes them.
- [ ] **4.7** Unset `CF_API_TOKEN` in a subshell and run any subcommand
      — expect a clean `ClickException` naming the missing variable. No
      traceback.
- [ ] **4.8** Cross-check: `./material_core/scripts/manage-tokens.sh
      list` should show the same tokens as `matctl token list`
      throughout Phase 4. Confirms both clients see the same KV state
      and that `matctl token` hasn't corrupted anything the shell
      script can still read.

## Phase 5 — Production verification gate

- [ ] **5.1** Issue one real token for the current semester via
      `matctl token issue` (not the shell script). Paste the URL into a
      fresh browser session and confirm the protected content loads as
      a student would see it. This is the gate called for by the
      REQ-006 notes ("until REQ-006 is verified in production").
- [ ] **5.2** Only after 5.1 passes does Phase 6 delete the shell
      script. If 5.1 fails, the shell script stays and REQ-006 remains
      OPEN pending a fix.

## Phase 6 — Cleanup and documentation

- [ ] **6.1** Delete `material_core/scripts/manage-tokens.sh` and
      `material_core/scripts/.env.example`. Keep `material_core/
      scripts/.env` — it holds the live credentials
      `_cloudflare.py` now reads.
- [ ] **6.2** Update `docs/administration.md`:
  - §7.1 / §7.2 / §7.3: replace every `./scripts/manage-tokens.sh
    <cmd>` with `matctl token <cmd>`.
  - §2 architecture diagram: `Mgmt[manage-tokens.sh<br/>local CLI]` →
    `Mgmt[matctl token<br/>local CLI]`.
  - §2 component table: "manage-tokens.sh" row → "matctl token".
  - §3 / §5 ops reference tables: same rename.
  - §5 "dead keys" line: `matctl token revoke <token>` instead of
    `scripts/manage-tokens.sh revoke`.
- [ ] **6.3** Update `material-core/CLAUDE.md`:
  - "matctl CLI" block: add a `matctl token issue/list/revoke/show`
    entry.
  - "Current status" line: bump to `REQ-006 DONE`.

## Phase 7 — Close out REQ-006

- [ ] **7.1** Tick acceptance criteria in
      `docs/requirements/REQ-006.md`, set `Status: DONE`, fill
      `Completed` (`2026-04-??`) and `Verified by` (e.g. "manual
      issue/list/revoke cycle + live browser check against real KV
      2026-04-??").
- [ ] **7.2** Update `REQUIREMENTS_INDEX.md` to match.
- [ ] **7.3** Tag `material-core` `v0.3.0` (new command group = minor
      bump per the semver rule in `CLAUDE.md`). Pinned-ref bump in
      `material/.github/workflows/publish.yml` is **optional** — CI in
      `material` does not invoke `matctl token` today. If skipped, note
      it in the commit message so the mismatch is intentional and
      documented.

---

## Commit strategy

Three commits in `material-core`:

1. **Phases 1–3** — `httpx` dep + `_cloudflare.py` + `cli.py` wiring.
   All interlocked, ships as one commit.
2. **Phase 6** — script deletion + doc updates. Separate commit so the
   code review of commit 1 stays focused on the new Python.
3. **Phase 7** — REQ status + index + version bump + tag. Standard
   close-out.

No commit in `material` unless 7.3 opts into the pinned-ref bump.

## Risks and mitigations

- **`scripts/.env` not resolvable via `importlib.resources` in editable
  pipx installs.** The `link` command already uses `files(
  "material_core")` against `shared/` and works fine, so the same
  mechanism should resolve `scripts/.env`. Fallback: `Path(__file__).
  parent / "scripts" / ".env"` — same reliability as the shell script's
  own lookup.
- **`httpx.Client` default timeout hangs on flaky networks.** Set
  `timeout=10.0` explicitly. Cloudflare KV PUT/GET are sub-second in
  practice; 10s catches network weirdness without hanging forever.
- **Alphabet change from `[a-z0-9]` to hex affects existing tokens.**
  Non-issue — tokens are opaque keys, never compared or decoded. Only
  *new* tokens use the hex generator; old ones keep working verbatim.
- **`list` is O(N) HTTP round trips.** Same as the shell script.
  Acceptable at current scale (dozens of tokens). Cloudflare KV bulk
  API is a future optimization, not a REQ-006 concern.
- **Cloudflare API response shape drifts.** The shell script parses
  responses with `grep`, so it is equally exposed. `_cloudflare.py`
  uses `response.json()` + explicit key lookups, which fails loudly on
  a schema change rather than silently returning empty strings —
  arguably an improvement.

## Explicitly out of scope (deferred to later REQs if needed)

- Rewriting the Cloudflare Worker (`cloudflare/worker.js`) — untouched.
- `COOKIE_SECRET` rotation tooling — mentioned in revoke help text
  only; automation is a future REQ.
- Moving `scripts/.env` to `~/.config/matctl/` or similar — existing
  location works; relocation is its own REQ.
- Bulk operations (`issue --count N`, `revoke --course X`,
  `revoke --expired`) — not in the shell script, not in REQ-006.
- A pytest harness for `_cloudflare.py` — this repo has no test
  infrastructure today; adding it is its own requirement.
- Switching from `httpx` sync to async — four sequential admin calls
  do not benefit from async; revisit if bulk operations land.
