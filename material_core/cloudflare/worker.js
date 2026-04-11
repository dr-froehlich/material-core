/**
 * Cloudflare Worker — Token-gated access for material.professorfroehlich.de
 *
 * Flow:
 *   1. Check for a valid signed session cookie (fast path, no KV read)
 *   2. Check ?token= query param → KV lookup → verify course matches URL path
 *   3. Valid: set cookie, redirect to clean URL (no token param)
 *   4. Invalid/missing: serve 403 page
 *
 * Environment bindings required:
 *   LECTURE_TOKENS  — KV namespace (key: "tok:<token>", value: JSON)
 *   COOKIE_SECRET   — random 32-char hex string for HMAC signing
 *
 * KV value schema:
 *   { "course": "digital-und-mikrocomputertechnik", "label": "WS2025/26",
 *     "issued": "2025-09-01", "expires": "2026-09-30" }
 *   Use course = "*" to grant access to all courses.
 */

const COOKIE_NAME = "mat_session";
const COOKIE_MAX_AGE = 60 * 60 * 24 * 365; // 1 year in seconds

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Extract the course slug from the first path segment:
    //   /digital-und-mikrocomputertechnik/... → "digital-und-mikrocomputertechnik"
    const course = url.pathname.split("/").filter(Boolean)[0] || null;

    // No course prefix → nothing to protect (e.g. bare domain root, favicon)
    if (!course) {
      return fetch(request);
    }

    // 1. Fast path: valid signed cookie
    const cookieHeader = request.headers.get("Cookie") || "";
    const sessionValue = getCookie(cookieHeader, COOKIE_NAME);
    if (sessionValue) {
      const payload = await verifySessionCookie(sessionValue, course, env.COOKIE_SECRET);
      if (payload) {
        return fetch(request); // authenticated, pass through to origin
      }
    }

    // 2. Token in query param
    const token = url.searchParams.get("token");
    if (token) {
      const record = await lookupToken(token, env.LECTURE_TOKENS);
      if (record && isAuthorized(record, course)) {
        // Issue session cookie and redirect to clean URL (no ?token=)
        const cleanUrl = new URL(request.url);
        cleanUrl.searchParams.delete("token");
        const cookieValue = await makeSessionCookie(course, env.COOKIE_SECRET);
        return new Response(null, {
          status: 302,
          headers: {
            Location: cleanUrl.toString(),
            "Set-Cookie": buildCookieHeader(cookieValue),
            "Cache-Control": "no-store",
          },
        });
      }
      // Token present but invalid — fall through to 403
    }

    // 3. No valid auth
    return forbidden(course);
  },
};

// ---------------------------------------------------------------------------
// KV helpers
// ---------------------------------------------------------------------------

async function lookupToken(token, kv) {
  try {
    const raw = await kv.get(`tok:${token}`);
    if (!raw) return null;
    const record = JSON.parse(raw);
    // Check expiry
    if (record.expires && new Date(record.expires) < new Date()) return null;
    return record;
  } catch {
    return null;
  }
}

function isAuthorized(record, course) {
  return record.course === "*" || record.course === course;
}

// ---------------------------------------------------------------------------
// Cookie helpers
// ---------------------------------------------------------------------------

function getCookie(cookieHeader, name) {
  const match = cookieHeader
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${name}=`));
  return match ? match.slice(name.length + 1) : null;
}

/**
 * Cookie value format: "<course>.<expiry-unix>.<hmac-hex>"
 * Signed with HMAC-SHA256 over "<course>.<expiry-unix>" using COOKIE_SECRET.
 */
async function makeSessionCookie(course, secret) {
  const expiry = Math.floor(Date.now() / 1000) + COOKIE_MAX_AGE;
  const message = `${course}.${expiry}`;
  const sig = await hmacHex(secret, message);
  return `${message}.${sig}`;
}

async function verifySessionCookie(value, course, secret) {
  const parts = value.split(".");
  if (parts.length < 3) return null;
  const sig = parts.pop();
  const message = parts.join(".");
  const [cookieCourse, expiryStr] = parts;
  const expiry = parseInt(expiryStr, 10);
  if (isNaN(expiry) || expiry < Math.floor(Date.now() / 1000)) return null;
  if (cookieCourse !== course && cookieCourse !== "*") return null;
  const expectedSig = await hmacHex(secret, message);
  // Constant-time comparison
  if (sig.length !== expectedSig.length) return null;
  let diff = 0;
  for (let i = 0; i < sig.length; i++) diff |= sig.charCodeAt(i) ^ expectedSig.charCodeAt(i);
  if (diff !== 0) return null;
  return { course: cookieCourse, expiry };
}

function buildCookieHeader(value) {
  return [
    `${COOKIE_NAME}=${value}`,
    `Max-Age=${COOKIE_MAX_AGE}`,
    "Path=/",
    "HttpOnly",
    "Secure",
    "SameSite=Lax",
  ].join("; ");
}

// ---------------------------------------------------------------------------
// Crypto
// ---------------------------------------------------------------------------

async function hmacHex(secret, message) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

// ---------------------------------------------------------------------------
// 403 page
// ---------------------------------------------------------------------------

function forbidden(course) {
  const html = `<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Zugriff verweigert</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: system-ui, sans-serif;
      background: #1a4273;
      color: #e8f0f7;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 2rem;
    }
    .card {
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.15);
      border-radius: 12px;
      padding: 2.5rem 3rem;
      max-width: 480px;
      text-align: center;
    }
    h1 { font-size: 1.5rem; margin-bottom: 1rem; color: #e87722; }
    p  { line-height: 1.6; margin-bottom: 0.75rem; }
    .hint { font-size: 0.875rem; opacity: 0.7; margin-top: 1.5rem; }
    code { background: rgba(255,255,255,0.1); padding: 0.1em 0.4em; border-radius: 4px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Zugriff nicht möglich</h1>
    <p>Diese Seite ist nur mit einem gültigen Zugangslink erreichbar.</p>
    <p>Den Link findesn Sie im zugehörigen <strong>iLearn-Kurs</strong>.</p>
    <p class="hint">Kurs: <code>${escapeHtml(course)}</code></p>
  </div>
</body>
</html>`;
  return new Response(html, {
    status: 403,
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
  });
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
