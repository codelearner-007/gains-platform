/**
 * Schoology Assessment Results Exporter
 *
 * Faithful port of the legacy Power Automate Desktop bot, retargeted for the
 * Gains Platform:
 *   - Same API filters (type=assessment, due within window, grading category regex)
 *   - Same export flow (one assessment at a time: export -> download 3 CSVs -> upload -> next)
 *   - Config sourced from the backend (GET /ingestion/scraper-config), not schools.json
 *   - Uploads to Supabase Storage (not Azure Blob) at the frozen storage key:
 *       <short_name>/<session>/<category>/<subject>/<grade>/<section>/<originalFilename>
 *   - After a school's uploads finish: POST /ingestion/scraper-complete (trigger)
 *
 * Hardening (v2):
 *   - Per-school credential resolution: credential_ref ?? short_name → SCHOOLOGY_CREDENTIALS
 *     JSON map → "default" → legacy flat env → HARD FAIL (never a silent 0-assessment run).
 *   - Bounded concurrency (SCRAPER_CONCURRENCY, default 2, cap 4) with per-school
 *     failure isolation, a result ledger, transient retry, and a non-zero exit if any
 *     school failed. Each school owns its own browser + credentials.
 *
 * Usage:
 *   node schoology-exporter.js                          # Run all active schools
 *   node schoology-exporter.js --school "Athenian"      # Run one school (partial name match)
 *   node schoology-exporter.js --headed                 # Visible browser
 *   node schoology-exporter.js --dry-run                # Discovery only, no export/upload
 */
// playwright costs ~305 ms to require and is only needed once a browser is
// actually launched — `--help` and `--dry-run` never are. Required lazily in
// SchoologySession.init().
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const https = require("https");
const { createClient } = require("@supabase/supabase-js");
require("dotenv").config();

const { Logger } = require("./lib/logger");
const { paginateAll, DEFAULT_PAGE_LIMIT } = require("./lib/paginate");
const {
  buildRelativePrefix,
  buildRelativeKey,
  safeSegment,
  academicSession,
  computeDueWindow,
  isDueInWindow,
} = require("./lib/paths");
const { sendRunSummary, overallStatus } = require("./lib/notify");

// ── CLI flags ────────────────────────────────────────────────────────────────
// A flag that TAKES a value must reject a missing/flag-shaped operand. The old
// `argv[indexOf(flag)+1]` form silently yielded undefined for a trailing
// `--school`, which fell through to "no filter" and swept EVERY school — the
// opposite of what the operator asked for.
function flagValue(name) {
  const i = process.argv.indexOf(name);
  if (i === -1) return null;
  const v = process.argv[i + 1];
  if (v === undefined || v.startsWith("--")) {
    console.error(`ERROR: ${name} requires a value (e.g. ${name} "Athenian")`);
    process.exit(2);
  }
  return v;
}

function intFlag(name) {
  const raw = flagValue(name);
  if (raw === null) return null;
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n) || n < 0) {
    console.error(`ERROR: ${name} must be a non-negative integer (got "${raw}")`);
    process.exit(2);
  }
  return n;
}

const USAGE = `
Schoology Assessment Results Exporter

Usage: node schoology-exporter.js [options]

Selection
  --school <name>        Only this school (case-insensitive substring of school name)
  --assessment <text>    Only assessments whose title contains <text> (case-insensitive)

Due-date window  (default: due within the school's due_date_window_days, up to today)
  --window-days <n>      Override due_date_window_days for this run
  --due-until <date>     Extend the window's upper bound to YYYY-MM-DD. Use this to
                         pick up an assessment dated in the FUTURE, which the default
                         window excludes.
  --include-undated      Also include assessments that have NO due date. Schoology
                         leaves the due date empty on many hand-made test assessments;
                         without this they are invisible to discovery.

Execution
  --dry-run              Discovery only: no browser, no export, no upload, no trigger
  --headed               Visible browser (default: headless)
  -h, --help             Show this help
`;

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  console.log(USAGE.trim());
  process.exit(0);
}

const HEADED = process.argv.includes("--headed");
const DRY_RUN = process.argv.includes("--dry-run");
const SCHOOL_FILTER = flagValue("--school");
const ASSESSMENT_FILTER = flagValue("--assessment");
const WINDOW_DAYS_OVERRIDE = intFlag("--window-days");
const INCLUDE_UNDATED = process.argv.includes("--include-undated");
const DUE_UNTIL = (() => {
  const raw = flagValue("--due-until");
  if (raw === null) return null;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    console.error(`ERROR: --due-until must be YYYY-MM-DD (got "${raw}")`);
    process.exit(2);
  }
  return raw;
})();

// ── Environment ──────────────────────────────────────────────────────────────
const SCHOOLOGY_URL = process.env.SCHOOLOGY_URL || "https://app.schoology.com";
const BACKEND_BASE_URL = (process.env.BACKEND_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const INGESTION_TRIGGER_SECRET = process.env.INGESTION_TRIGGER_SECRET || "";
const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY;

const DOWNLOAD_DIR = process.env.DOWNLOAD_DIR || path.join(__dirname, "downloads");
const SCREENSHOT_DIR = path.join(__dirname, "screenshots");

// Bounded scraper concurrency: default 2, hard cap 4 (each school owns a browser).
const SCRAPER_CONCURRENCY = (() => {
  const raw = parseInt(process.env.SCRAPER_CONCURRENCY || "2", 10);
  if (!Number.isFinite(raw) || raw < 1) return 2;
  return Math.min(raw, 4);
})();

// Transient-failure retry policy (§8): one retry, 30s backoff. Credential
// rejection is fatal and never retried.
const TRANSIENT_RETRY_ATTEMPTS = 1;
const TRANSIENT_RETRY_BACKOFF_MS = 30000;

// The three CSV types the backend ingests. FROZEN CONTRACT: the backend routes a
// file to its parser purely by this filename prefix
// (backend/app/jobs/file_path_parser.py::classify_file_type), and an unrecognised
// prefix is a hard PathParseError. The export form ticks a fourth box whose
// output has no parser, so it is downloaded and then dropped rather than
// uploaded into a bucket holding student PII.
const WANTED_FILE_PREFIXES = ["Question-Data", "Student-Submissions", "Submission-Summary"];

// ── Helpers ─────────────────────────────────────────────────────────────────
function ensureDir(dir) { if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true }); }
// Root logger. A run id is bound once so every line can be joined to the
// ingestion_runs row the backend creates, and to the notification email.
const RUN_ID = crypto.randomBytes(4).toString("hex");
const rootLog = new Logger({ runId: RUN_ID });
// `log(msg)` is kept as an info-level shim so the existing call sites read the
// same; new code should prefer an explicitly-levelled logger with context.
function log(msg) { rootLog.info(msg); }
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

// Per-school discovery stats, read by the run summary + notification email.
const discoveryStats = new Map();
// Every object key that reached storage this run — listed in the email so an
// operator can eyeball the folder shape without opening the bucket.
const uploadedKeys = [];




// ── Credential resolution (per-school, §7) ────────────────────────────────────
// A resolved credential set carries the 4 Schoology values plus the ref it came
// from (for logging). Secrets live ONLY in the scraper env, never in the DB or
// any backend payload.

// Parse the SCHOOLOGY_CREDENTIALS JSON map once. Shape:
//   {"<ref>":{"username","password","consumer_key","consumer_secret"}, "default":{...}}
// Invalid JSON is a hard, loud failure — a silent empty map would degrade every
// school to the "silent 0 assessments" bug this fix exists to close (F16).
const CREDENTIAL_MAP = (() => {
  const raw = process.env.SCHOOLOGY_CREDENTIALS;
  if (!raw || !raw.trim()) return null;
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    throw new Error(`SCHOOLOGY_CREDENTIALS is not valid JSON: ${err.message}`);
  }
  if (typeof parsed !== "object" || Array.isArray(parsed) || parsed === null) {
    throw new Error("SCHOOLOGY_CREDENTIALS must be a JSON object mapping ref → credentials");
  }
  return parsed;
})();

// Legacy flat-env fallback (single shared admin identity). Present iff all four
// values are set.
function legacyFlatCredentials() {
  const c = {
    username: process.env.SCHOOLOGY_USERNAME,
    password: process.env.SCHOOLOGY_PASSWORD,
    consumerKey: process.env.SCHOOLOGY_CONSUMER_KEY,
    consumerSecret: process.env.SCHOOLOGY_CONSUMER_SECRET,
  };
  if (c.username && c.password && c.consumerKey && c.consumerSecret) return c;
  return null;
}

// Normalize one map entry (username/password/consumer_key/consumer_secret) into
// the internal camelCase shape. Returns null if the entry is missing any field.
function normalizeMapEntry(entry) {
  if (!entry || typeof entry !== "object") return null;
  const c = {
    username: entry.username,
    password: entry.password,
    consumerKey: entry.consumer_key,
    consumerSecret: entry.consumer_secret,
  };
  if (c.username && c.password && c.consumerKey && c.consumerSecret) return c;
  return null;
}

// Resolve credentials for one school, throwing loudly on no match.
//   credential_ref ?? short_name → SCHOOLOGY_CREDENTIALS[ref]
//     → SCHOOLOGY_CREDENTIALS["default"] → legacy flat env → HARD FAIL.
function resolveCredentials(school) {
  const ref = school.credentialRef || school.shortName;

  if (CREDENTIAL_MAP) {
    const byRef = normalizeMapEntry(CREDENTIAL_MAP[ref]);
    if (byRef) return { ...byRef, source: `SCHOOLOGY_CREDENTIALS[${ref}]` };

    const byDefault = normalizeMapEntry(CREDENTIAL_MAP.default);
    if (byDefault) return { ...byDefault, source: "SCHOOLOGY_CREDENTIALS[default]" };
  }

  const legacy = legacyFlatCredentials();
  if (legacy) return { ...legacy, source: "legacy flat env" };

  throw new Error(
    `no Schoology credentials for school "${school.name}" (ref="${ref}"): ` +
    `set SCHOOLOGY_CREDENTIALS["${ref}"] or SCHOOLOGY_CREDENTIALS["default"] ` +
    `or the legacy SCHOOLOGY_USERNAME/PASSWORD/CONSUMER_KEY/CONSUMER_SECRET vars`,
  );
}

// ── Error classification (§8) ─────────────────────────────────────────────────
// A credential rejection (login re-render / API 401) is fatal for the school:
// distinct 'credential' class, never retried. Everything else is 'transient'
// (one retry, 30s backoff).
class CredentialError extends Error {
  constructor(message) { super(message); this.name = "CredentialError"; this.errorClass = "credential"; }
}
function classifyError(err) {
  return err && err.errorClass === "credential" ? "credential" : "transient";
}

// ── Backend contract (frozen) ────────────────────────────────────────────────
// GET /api/v1/ingestion/scraper-config -> { storage:{bucket}, schools:[...] }
// POST /api/v1/ingestion/scraper-complete { short_name, note? } -> 202
// Auth header: X-Ingestion-Secret: <INGESTION_TRIGGER_SECRET>
async function fetchScraperConfig() {
  const url = `${BACKEND_BASE_URL}/api/v1/ingestion/scraper-config`;
  const res = await fetch(url, {
    method: "GET",
    headers: { "X-Ingestion-Secret": INGESTION_TRIGGER_SECRET, Accept: "application/json" },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`scraper-config failed: HTTP ${res.status} ${body.substring(0, 200)}`);
  }
  return res.json();
}

// scraper-complete POST with bounded retry (§8): up to 3 attempts, exponential
// backoff, honoring a Retry-After header on 429. Throws after the last attempt.
async function postScraperComplete(shortName, note) {
  const url = `${BACKEND_BASE_URL}/api/v1/ingestion/scraper-complete`;
  const maxAttempts = 3;
  let lastErr;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    let res;
    try {
      res = await fetch(url, {
        method: "POST",
        headers: {
          "X-Ingestion-Secret": INGESTION_TRIGGER_SECRET,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(note ? { short_name: shortName, note } : { short_name: shortName }),
      });
    } catch (err) {
      // Network error — retryable.
      lastErr = err;
      if (attempt < maxAttempts) {
        await sleep(backoffDelay(attempt, null));
        continue;
      }
      throw new Error(`scraper-complete failed: ${err.message}`);
    }

    const body = await res.text().catch(() => "");
    if (res.ok) return body;

    lastErr = new Error(`scraper-complete failed: HTTP ${res.status} ${body.substring(0, 200)}`);

    // 429 → honor Retry-After; other 5xx → retry with backoff; 4xx (not 429) → fail fast.
    const retryable = res.status === 429 || res.status >= 500;
    if (!retryable || attempt >= maxAttempts) throw lastErr;

    const retryAfter = res.status === 429 ? parseRetryAfter(res.headers.get("retry-after")) : null;
    await sleep(backoffDelay(attempt, retryAfter));
  }

  throw lastErr;
}

// Exponential backoff (1s, 2s, 4s…) capped at 30s; a Retry-After hint wins.
function backoffDelay(attempt, retryAfterMs) {
  if (retryAfterMs != null) return retryAfterMs;
  return Math.min(1000 * 2 ** (attempt - 1), 30000);
}

// Parse a Retry-After header (delta-seconds or HTTP-date) → ms, or null.
function parseRetryAfter(value) {
  if (!value) return null;
  const secs = Number(value);
  if (Number.isFinite(secs)) return Math.max(0, secs * 1000);
  const when = Date.parse(value);
  if (!Number.isNaN(when)) return Math.max(0, when - Date.now());
  return null;
}

// ── OAuth 1.0a ──────────────────────────────────────────────────────────────
function percentEncode(s) {
  return encodeURIComponent(s).replace(/!/g, "%21").replace(/\*/g, "%2A")
    .replace(/'/g, "%27").replace(/\(/g, "%28").replace(/\)/g, "%29");
}

// apiGet now takes the resolved per-school credentials (no inline env reads), so
// concurrent schools never cross-contaminate keys.
// One HTTP attempt. Resolves {status, data} — never swallows the status code, so
// the caller can distinguish "credentials rejected" from "Schoology is busy"
// from "this collection is genuinely empty".
function apiGetOnce(creds, endpoint, redirectsLeft = 3) {
  const key = creds && creds.consumerKey;
  const secret = creds && creds.consumerSecret;
  if (!key || !secret) return Promise.resolve({ status: 0, data: null });

  return new Promise((resolve) => {
    const url = "https://api.schoology.com/v1" + endpoint;
    const op = {
      oauth_consumer_key: key, oauth_nonce: crypto.randomBytes(16).toString("hex"),
      oauth_signature_method: "HMAC-SHA1", oauth_timestamp: Math.floor(Date.now() / 1000).toString(),
      oauth_token: "", oauth_version: "1.0",
    };
    const parsed = new URL(url);
    const all = { ...op };
    for (const [k, v] of parsed.searchParams.entries()) all[k] = v;
    const sorted = Object.keys(all).sort().map((k) => percentEncode(k) + "=" + percentEncode(all[k])).join("&");
    const base = "GET&" + percentEncode(parsed.protocol + "//" + parsed.host + parsed.pathname) + "&" + percentEncode(sorted);
    op.oauth_signature = crypto.createHmac("sha1", percentEncode(secret) + "&").update(base).digest("base64");
    const auth = "OAuth " + Object.keys(op).sort().map((k) => percentEncode(k) + '="' + percentEncode(op[k]) + '"').join(", ");

    const req = https.request({
      hostname: parsed.hostname, path: parsed.pathname + parsed.search,
      method: "GET", headers: { Authorization: auth, Accept: "application/json" },
    }, (res) => {
      if ([301, 302, 303].includes(res.statusCode) && res.headers.location) {
        if (redirectsLeft <= 0) {
          // A Location that resolves to itself used to recurse without bound.
          resolve({ status: 508, data: null });
          return;
        }
        let loc = res.headers.location;
        if (loc.startsWith("http")) {
          // MUST keep the query string. Taking only `.pathname` dropped
          // building_id / start_id / limit, so a redirected /courses page came
          // back UNSCOPED — other buildings' courses filed under this school —
          // and the paginator cannot compensate for a filter lost inside get().
          const u = new URL(loc);
          loc = u.pathname + (u.search || "");
        }
        resolve(apiGetOnce(creds, loc.replace(/^\/v1/, ""), redirectsLeft - 1));
        return;
      }
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => {
        if (res.statusCode !== 200) {
          resolve({ status: res.statusCode, data: null, retryAfter: res.headers["retry-after"] });
          return;
        }
        try {
          resolve({ status: 200, data: JSON.parse(body) });
        } catch {
          // 200 with an unparseable body is a server-side problem, not an empty
          // collection — surface it as retryable rather than as "no results".
          resolve({ status: 502, data: null });
        }
      });
    });
    // status 0 == transport failure (DNS, reset, timeout); retryable.
    req.on("error", () => resolve({ status: 0, data: null }));
    req.setTimeout(15000, () => { req.destroy(); resolve({ status: 0, data: null }); });
    req.end();
  });
}

/**
 * apiGet with status-aware retries.
 *
 * The original collapsed EVERY failure — 401, 429, 500, timeout — to `null`,
 * which produced two distinct bugs. On the first courses page a `null` was
 * reported as a CredentialError, so a transient 429 became a fatal "bad
 * credentials" with no retry. On any later page, `null` was indistinguishable
 * from an empty collection, so discovery silently returned FEWER sections or
 * assignments and the run reported success having scraped a subset.
 *
 * Now: auth failures throw CredentialError (never retried), transient failures
 * are retried with backoff and then throw, and only a real 200 returns data.
 */
async function apiGet(creds, endpoint) {
  const maxAttempts = 3;
  let last = null;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const res = await apiGetOnce(creds, endpoint);
    last = res;

    if (res.status === 200) return res.data;

    if (res.status === 401 || res.status === 403) {
      throw new CredentialError(
        `Schoology API rejected credentials (${creds.source}) — HTTP ${res.status} on ${endpoint}`,
      );
    }

    // 404 is a real answer for an absent collection, not a failure to retry.
    if (res.status === 404) return null;

    const retryable = res.status === 0 || res.status === 429 || res.status >= 500;
    if (!retryable || attempt === maxAttempts) break;

    // Reuse the helpers postScraperComplete already uses. The inline version this
    // replaces handled only delta-seconds, so a `Retry-After: <HTTP-date>` was
    // discarded and the wait silently fell back to plain exponential backoff.
    const backoffMs = backoffDelay(attempt, parseRetryAfter(res.retryAfter));
    rootLog.warn("Schoology API call failed — retrying", {
      status: res.status || "network-error", endpoint,
      attempt: `${attempt}/${maxAttempts - 1}`, backoffSec: Math.round(backoffMs / 1000),
    });
    await sleep(backoffMs);
  }

  throw new Error(
    `Schoology API failed after ${maxAttempts} attempt(s): `
    + `HTTP ${last ? last.status || "network error" : "unknown"} on ${endpoint}`,
  );
}

// ── Schoology API mappings (from production C# code TenantConfigAppService.cs) ──

// subject_area int → subject name (production: subjectMapping dictionary)
const SUBJECT_CODE_MAP = {
  0: "Other", 1: "Health & Physical Education", 2: "Language Arts", 3: "Mathematics",
  4: "Professional Development", 5: "Science", 6: "Social Studies",
  7: "Special Education", 8: "Technology", 9: "Arts",
};

// grade_level_range_start int → grade name (production: gradeLevelMapping dictionary)
const GRADE_CODE_MAP = {
  0: "No grade level/remove grade level", 1: "Pre-K", 2: "Grade K",
  3: "Grade 1", 4: "Grade 2", 5: "Grade 3", 6: "Grade 4", 7: "Grade 5",
  8: "Grade 6", 9: "Grade 7", 10: "Grade 8", 11: "Grade 9", 12: "Grade 10",
  13: "Grade 11", 14: "Grade 12", 15: "Higher-Ed",
};

// ── Discovery: Exact replica of TenantConfigAppService.GetSchoologyDataAsync() ──
async function discoverAssessments(school, creds) {
  // School-scoped logger: every discovery line now names the school, which in a
  // multi-school run was previously impossible to tell from the log alone.
  const slog = rootLog.child({ school: school.shortName });
  slog.info("discovery started");

  // Production: var currentDate = DateTime.UtcNow;
  const currentDate = new Date();
  // Due window, in the SCHOOL's timezone (see computeDueWindow). `windowDays`
  // falls back to 14 when the column is null — `null * 86400000` is 0, which
  // would silently collapse the window to "due exactly today".
  const windowDays = WINDOW_DAYS_OVERRIDE !== null
    ? WINDOW_DAYS_OVERRIDE
    : (Number.isFinite(school.dueDateWindowDays) ? school.dueDateWindowDays : 14);
  const dueWindow = computeDueWindow({
    timezone: school.timezone,
    windowDays,
    dueUntil: DUE_UNTIL,
    now: currentDate,
  });
  // Academic year in the SCHOOL's timezone. Deriving it from the runner's clock
  // (the old `currentDate.getMonth()`) put a UTC container between 00:00 and
  // 04:00 ET, or any run near the 1 August rollover, in a DIFFERENT year than the
  // school — and session is the FIRST path segment, so every row would land under
  // the wrong academic year.
  const computedAcademicYear = academicSession(school.timezone, currentDate);
  const session = school.currentSession || computedAcademicYear;
  if (school.currentSession && school.currentSession !== computedAcademicYear) {
    // Worth one line: an override that disagrees with the computed year is either
    // a deliberate pin or a stale config, and only the operator can tell which.
    slog.info("session override differs from the computed academic year", {
      configured: school.currentSession, computed: computedAcademicYear,
    });
  }
  slog.info("discovery window", {
    timezone: school.timezone || "UTC",
    window: `${dueWindow.from}..${dueWindow.to}`,
    today: dueWindow.today,
    windowDays,
    session,
    dueUntil: DUE_UNTIL || undefined,
    includeUndated: INCLUDE_UNDATED || undefined,
    assessmentFilter: ASSESSMENT_FILTER || undefined,
  });

  // Production: categoryRegex from tenant config "LessonAssessments"
  // e.g. "(Chapter|lesson|Weekly|Module|Assessments)"
  const categoryRegex = new RegExp(school.gradingCategoryRegex, "i");
  slog.debug("category regex", { regex: school.gradingCategoryRegex });

  // Production: build validCombos from all subject x grade combinations.
  // Every (subjectCode, gradeCode) pair is valid — this is an existence gate to
  // map codes → names, not a real filter.
  const validComboSet = new Set(); // "subjectCode-gradeCode"
  for (const sc of Object.keys(SUBJECT_CODE_MAP)) {
    for (const gc of Object.keys(GRADE_CODE_MAP)) {
      validComboSet.add(`${sc}-${gc}`);
    }
  }

  // Production: coursePageLimit from tenant config (default 200)
  const coursePageLimit = school.coursePageLimit || DEFAULT_PAGE_LIMIT;

  // Discovery funnel. "0 assessments" is the single most confusing outcome a run
  // can produce, and previously the log went straight from "Courses: 106" to
  // "Assessments matching all filters: 0" with six silent drop points in between.
  // Every `continue` below increments exactly one counter, so the summary line
  // always accounts for the difference.
  const funnel = {
    courses: 0,
    coursesSkippedSubjectGrade: 0,
    coursesWithZeroSections: 0,
    sections: 0,
    sectionsSkippedNoMatchingCategory: 0,
    sectionsWithZeroCategories: 0,
    assignments: 0,
    notAssessmentType: 0,
    categoryUnmatched: 0,
    filteredByAssessmentFlag: 0,
    outsideDueWindow: 0,
    undatedExcluded: 0,
    futureDated: 0,
    badWebUrl: 0,
  };

  // Step 1: Paginate through courses
  // Production uses per-school API keys so only gets that school's courses.
  // We use a shared admin key, so filter by building_id to scope to one school.
  // MEASURED: Schoology returns `links.next` for /courses with building_id
  // STRIPPED (next = "/v1/courses?start_id=...&limit=..."). Following it verbatim
  // — which the old loop did — silently widens page 2+ beyond the requested
  // school. paginateAll re-applies `params` to every page, so the scope holds.
  if (!school.buildingId) {
    // Without a building filter, discovery returns whatever the credential can
    // see. That is only safe when the identity belongs to exactly one school.
    slog.warn(
      "school has no schoology_building_id — course discovery is UNSCOPED and will "
      + "include every building this credential can see",
      { credentialSource: creds.source },
    );
  }
  const coursesPage = await paginateAll({
    get: (url) => apiGet(creds, url),
    endpoint: "/courses",
    collection: "course",
    params: {
      start_id: 0,
      limit: coursePageLimit,
      ...(school.buildingId ? { building_id: school.buildingId } : {}),
    },
    log: slog,
  });
  const allCourses = coursesPage.items;
  funnel.courses = allCourses.length;
  slog.info("courses discovered", {
    count: allCourses.length, pages: coursesPage.pages, scoped: Boolean(school.buildingId),
  });

  const assignmentUrls = new Map(); // key "{id}:{path}" (same dedup as Set), value: metadata
  // Sanitised-segment warnings, deduped, surfaced in the summary + email so a
  // Schoology rename that reshapes a path is visible without reading the log.
  const keyWarnings = new Set();

  for (const course of allCourses) {
    // Production: check if (subject_area, grade_level) combo is valid
    const subjectArea = course.subject_area ?? -1;
    const gradeLevel = course.grade_level_range_start ?? -1;
    const comboKey = `${subjectArea}-${gradeLevel}`;
    if (!validComboSet.has(comboKey)) {
      // Reached when Schoology reports a subject_area / grade_level code that is
      // absent from the maps (a new code, or null). The WHOLE course is skipped,
      // so this must be visible — it was previously silent.
      funnel.coursesSkippedSubjectGrade += 1;
      slog.warn("course skipped: unmapped subject_area/grade_level code", {
        course: course.id, title: course.title,
        subject_area: course.subject_area, grade_level_range_start: course.grade_level_range_start,
      });
      continue;
    }

    const subjectName = SUBJECT_CODE_MAP[subjectArea] || "Other";
    const gradeName = GRADE_CODE_MAP[gradeLevel] || "No grade level/remove grade level";

    const courseId = course.id;

    // Step 2: Get sections for this course.
    // MEASURED: this endpoint defaults to limit=20 and returns `total`. The old
    // call sent no limit and never read links.next, so a course with more than 20
    // sections silently lost the rest — and with them every assessment inside.
    const sectionsPage = await paginateAll({
      get: (url) => apiGet(creds, url),
      endpoint: `/courses/${courseId}/sections`,
      collection: "section",
      params: { start: 0, limit: coursePageLimit },
      log: slog,
    });
    if (!sectionsPage.items.length) {
      // Keep the funnel's stated invariant true: every `continue` increments
      // exactly one counter, or the breakdown stops adding up.
      funnel.coursesWithZeroSections += 1;
      continue;
    }
    funnel.sections += sectionsPage.items.length;

    for (const section of sectionsPage.items) {
      const sectionId = section.id;
      // Production: sectionName from section_code, fallback to section_title
      const sectionCode = section.section_code;
      const sectionTitle = section.section_title || "Unknown Section";
      const rawSectionName = sectionCode && sectionCode.trim() ? sectionCode : sectionTitle;
      // Deliberately NOT pre-sanitised: buildRelativePrefix sanitises every segment
      // and reports what it changed. Cleaning it here first made the value already
      // clean, so a "/" in a section_code was rewritten with no keyWarning — the one
      // segment admins rename most often was the one without an audit trail.
      const sectionName = `Sec ${rawSectionName}`;

      // Step 3: Get grading categories.
      // MEASURED: this endpoint returned NO `total` and NO `links` on a
      // 4-category section, which is evidence it is unpaginated — but that was
      // only observed for a small set, so it cannot be assumed. `expectAll` warns
      // loudly and follows the link if one ever appears, instead of truncating.
      //
      // Truncation here has the widest blast radius in the file: the section GATE
      // below skips the WHOLE section when no returned title matches the regex,
      // so a matching category on an unread page silently drops every assessment
      // in that section.
      const catsPage = await paginateAll({
        get: (url) => apiGet(creds, url),
        endpoint: `/sections/${sectionId}/grading_categories`,
        collection: "grading_category",
        params: { limit: coursePageLimit },
        expectAll: true,
        log: slog,
      });
      const gradingCategories = catsPage.items;
      if (gradingCategories.length === 0) funnel.sectionsWithZeroCategories += 1;

      // Production: build category map {id → title}
      const gradingCategoryMap = {};
      for (const gc of gradingCategories) {
        if (gc.id && gc.title) gradingCategoryMap[String(gc.id)] = gc.title;
      }

      // Production: check if ANY category title matches the regex
      const matchingCategories = gradingCategories.filter((gc) => categoryRegex.test(gc.title || ""));
      if (matchingCategories.length === 0) {
        funnel.sectionsSkippedNoMatchingCategory += 1;
        slog.debug("section skipped: no grading category matches the regex", {
          section: sectionId,
          categories: gradingCategories.map((gc) => gc.title).join(" | ") || "(none)",
        });
        continue;
      }

      // Step 4: Assignments. MEASURED: defaults to limit=20 and reports `total`
      // (one real section reported total=323). With limit=200 + links.next the
      // walk collects 323/323, and paginateAll now asserts collected == total so
      // a dropped page fails the school instead of quietly shortening the list.
      {
        const assignmentsPage = await paginateAll({
          get: (url) => apiGet(creds, url),
          endpoint: `/sections/${sectionId}/assignments`,
          collection: "assignment",
          params: { start: 0, limit: coursePageLimit },
          log: slog,
        });
        funnel.assignments += assignmentsPage.items.length;

        const validAssignments = assignmentsPage.items.filter((a) => {
          if (a.type !== "assessment") { funnel.notAssessmentType += 1; return false; }
          const catId = String(a.grading_category || "");
          if (!gradingCategoryMap[catId] || !categoryRegex.test(gradingCategoryMap[catId])) {
            funnel.categoryUnmatched += 1;
            return false;
          }
          return true;
        });

        for (const assignment of validAssignments) {
          // Optional operator filter, applied before the date test so a targeted
          // run reports "found but out of window" rather than a bare 0.
          if (ASSESSMENT_FILTER
            && !String(assignment.title || "").toLowerCase().includes(ASSESSMENT_FILTER.toLowerCase())) {
            funnel.filteredByAssessmentFlag += 1;
            continue;
          }

          if (!isDueInWindow(assignment.due, dueWindow,
            { includeUndated: INCLUDE_UNDATED, timezone: school.timezone })) {
            funnel.outsideDueWindow += 1;
            const day = assignment.due ? String(assignment.due).slice(0, 10) : null;
            if (!day) funnel.undatedExcluded += 1;
            else if (day > dueWindow.to) funnel.futureDated += 1;
            // A near-miss is the most common reason a run finds nothing, so it is
            // reported whether or not --assessment was passed. Previously this was
            // gated behind the flag and therefore silent on exactly the unattended
            // runs where nobody was watching. INFO when the operator named an
            // assessment (they are hunting it), DEBUG otherwise (could be hundreds).
            const msg = "assessment outside the due window";
            const fields = {
              title: assignment.title, due: assignment.due || "(none)",
              window: `${dueWindow.from}..${dueWindow.to}`,
              hint: "--due-until / --include-undated",
            };
            if (ASSESSMENT_FILTER) slog.info(msg, fields); else slog.debug(msg, fields);
            continue;
          }

          // Production: get assignmentId from web_url
          const webUrl = assignment.web_url || "";
          const assignmentId = webUrl.split("/").filter(Boolean).pop();
          if (!assignmentId || !/^\d+$/.test(assignmentId)) {
            // Previously dropped with no log and no counter, so a Schoology URL
            // format change would have looked like "no assessments exist".
            funnel.badWebUrl += 1;
            slog.warn("assessment skipped: could not read a numeric id from web_url", {
              title: assignment.title, web_url: webUrl || "(empty)", id: assignment.id,
            });
            continue;
          }

          // Category folder: per-school override (preserves the two-space literal
          // "1 - Lesson  Assessments") else the live grading-category title.
          const gradingCategoryId = String(assignment.grading_category || "");
          const categoryFolder = school.categoryFolderOverride || gradingCategoryMap[gradingCategoryId] || "Unknown Category";

          // Every segment goes through buildRelativeKey. Previously only the
          // SECTION was sanitised, while `session` and `categoryFolder` were
          // interpolated raw — and categoryFolder is a live Schoology
          // grading-category title, free text an admin can rename to
          // "Quizzes/Tests". A "/" there invents a path level, and the backend
          // parser is positional, so every later segment shifts and the rows land
          // under a WRONG subject/grade/section.
          const built = buildRelativePrefix({
            session, category: categoryFolder, subject: subjectName,
            grade: gradeName, section: sectionName,
          });
          for (const w of built.warnings) {
            // Once per DISTINCT rewrite. This sits in the per-assignment loop, so a
            // single admin rename previously emitted one line per discovered
            // assessment — thousands of near-identical lines in exactly the
            // scenario the warning exists to make visible.
            if (!keyWarnings.has(w)) {
              keyWarnings.add(w);
              slog.warn("storage key segment sanitised", { detail: w, assessment: assignmentId });
            }
          }
          const relPath = built.prefix; // includes the trailing "/"
          const formatted = `${assignmentId}:${relPath}`;
          if (!assignmentUrls.has(formatted)) {
            assignmentUrls.set(formatted, {
              // Keep the segment VALUES, not just the joined prefix: the upload
              // rebuilds the full key through buildRelativeKey so the filename is
              // sanitised too, and re-splitting the prefix string would be lossy.
              segments: {
                session, category: categoryFolder, subject: subjectName,
                grade: gradeName, section: sectionName,
              },
              title: assignment.title || "",
              due: assignment.due || "",
              courseTitle: course.title || "",
              sectionId: String(sectionId),
              sectionTitle,
              gradeName,
            });
          }
        }

      }
    }
  }

  // Convert to assessment objects
  const assessments = [];
  for (const [entry, meta] of assignmentUrls) {
    const colonIdx = entry.indexOf(":");
    const id = entry.substring(0, colonIdx);
    const relPath = entry.substring(colonIdx + 1);
    assessments.push({
      id,
      path: relPath,
      segments: meta.segments,
      title: meta.title,
      sectionId: meta.sectionId,
      sectionTitle: meta.sectionTitle,
      courseTitle: meta.courseTitle,
      due: meta.due,
      gradeName: meta.gradeName,
    });
  }

  // The funnel. Every drop point above increments exactly one counter, so a run
  // that discovers nothing says WHY instead of leaving the operator to guess.
  slog.info("discovery complete", {
    discovered: assessments.length,
    courses: funnel.courses,
    sections: funnel.sections,
    assignmentsSeen: funnel.assignments,
  });
  if (assessments.length === 0) {
    // WARN, not INFO: zero assessments is either a quiet day or a broken config,
    // and these counters are the only way to tell those apart.
    slog.warn("discovery found NO assessments — funnel breakdown follows", {
      courses: funnel.courses,
      coursesSkippedSubjectGrade: funnel.coursesSkippedSubjectGrade,
      coursesWithZeroSections: funnel.coursesWithZeroSections,
      sections: funnel.sections,
      sectionsSkippedNoMatchingCategory: funnel.sectionsSkippedNoMatchingCategory,
      sectionsWithZeroCategories: funnel.sectionsWithZeroCategories,
      assignmentsSeen: funnel.assignments,
      notAssessmentType: funnel.notAssessmentType,
      categoryUnmatched: funnel.categoryUnmatched,
      filteredByAssessmentFlag: funnel.filteredByAssessmentFlag,
      outsideDueWindow: funnel.outsideDueWindow,
      undatedExcluded: funnel.undatedExcluded,
      futureDated: funnel.futureDated,
      badWebUrl: funnel.badWebUrl,
    });
    if (funnel.futureDated > 0) {
      slog.warn(`${funnel.futureDated} assessment(s) are due AFTER the window — re-run with --due-until YYYY-MM-DD to include them`);
    }
    if (funnel.undatedExcluded > 0) {
      slog.warn(`${funnel.undatedExcluded} assessment(s) have NO due date — re-run with --include-undated to include them`);
    }
  }

  discoveryStats.set(school.shortName, {
    funnel, discovered: assessments.length, keyWarnings: [...keyWarnings],
  });
  return assessments;
}

// ── Playwright Session ──────────────────────────────────────────────────────
class SchoologySession {
  constructor(school, creds, supabase, bucket) {
    this.school = school;
    this.creds = creds;
    this.supabase = supabase;
    this.bucket = bucket;
    this.browser = null;
    this.context = null;
    this.page = null;
    this.uploadCount = 0;
    // Failure counters the batch summary + exit code read, so a run that
    // downloaded fine but failed every upload cannot report success.
    this.uploadErrors = 0;
    this.incompleteExports = [];
    this.exportFailures = [];
    // Per-school download dir: concurrent schools previously shared one folder
    // (and one screenshots folder), relying on a filename prefix to avoid
    // collisions.
    this.downloadDir = path.join(DOWNLOAD_DIR, this.school.shortName);
    // Every session line names the school; processAssessment re-binds it with the
    // assessment id so a failure is attributable without reading nearby lines.
    this.log = rootLog.child({ school: school.shortName });
  }

  async init() {
    ensureDir(this.downloadDir);
    ensureDir(SCREENSHOT_DIR);
    const { chromium } = require("playwright");
    this.browser = await chromium.launch({ headless: !HEADED, slowMo: HEADED ? 150 : 0 });
    this.context = await this.browser.newContext({ viewport: { width: 1920, height: 1080 }, acceptDownloads: true });
    this.page = await this.context.newPage();
    this.page.setDefaultTimeout(20000);
  }

  async close() { if (this.browser) await this.browser.close(); }

  async screenshot(name) {
    const dest = path.join(SCREENSHOT_DIR, `${name}.png`);
    try {
      await this.page.screenshot({ path: dest, fullPage: false });
      return dest;
    } catch (err) {
      // Still swallowed — a failed screenshot must not mask the real error — but
      // no longer silent, because "there should be a screenshot and there isn't"
      // is itself a clue.
      this.log.debug("could not capture debug screenshot", { dest, errMsg: err.message });
      return null;
    }
  }

  // Resilient click with fallback selectors
  async clickElement(selectors, description, opts = {}) {
    const { retries = 2, delay = 2000 } = opts;
    for (let attempt = 0; attempt <= retries; attempt++) {
      for (const sel of selectors) {
        try {
          const el = await this.page.waitForSelector(sel, { timeout: attempt === 0 ? 10000 : 5000, state: "visible" });
          if (el) { await el.click({ timeout: 5000 }); return true; }
        } catch { /* next */ }
      }
      if (attempt < retries) { await sleep(delay); }
    }
    return false;
  }

  // ── Login (identical to bot's login function) ───────────────────────────
  // Uses the per-school resolved credentials, not inline env reads. A rejected
  // login (form still present after submit) is a fatal credential error.
  async login() {
    this.log.info("login starting", { url: SCHOOLOGY_URL });
    await this.page.goto(SCHOOLOGY_URL, { waitUntil: "domcontentloaded", timeout: 30000 });
    await sleep(2000);

    if (this.page.url().includes("/home") || this.page.url().includes("/courses")) {
      this.log.debug("already logged in");
      return;
    }

    const loginForm = await this.page.$('input[name="mail"]');
    if (!loginForm) throw new Error(`Unexpected page: ${this.page.url()}`);

    await this.page.fill('input[name="mail"]', this.creds.username);
    await this.page.fill('input[name="pass"]', this.creds.password);
    await this.page.click('input[type="submit"][value="Log in"]');
    try {
      await this.page.waitForURL((url) => url.pathname.includes("/home") || url.pathname.includes("/courses"), { timeout: 30000 });
    } catch (err) {
      // Login form re-rendered / never navigated → credential rejection, fatal.
      if (await this.page.$('input[name="mail"]').catch(() => null)) {
        throw new CredentialError(`Schoology login rejected (${this.creds.source}) for "${this.school.name}"`);
      }
      throw err;
    }
    this.log.info("login successful");
  }

  /**
   * Click a required export-flow control, or record a typed export failure.
   *
   * The three call sites were 7 identical lines each (warn with `step`, push to
   * exportFailures, return false) differing only in two strings — and the `reason`
   * and `step` labels could drift apart.
   */
  async requireClick(selectors, { step, reason, id, title, retries, delay }) {
    const ok = await this.clickElement(selectors, step, { retries, delay });
    if (ok) return true;
    // A selector miss is how a Schoology UI change first shows up. Name the step,
    // or the run just looks like "this assessment had nothing to export".
    this.log.warn(`export aborted: ${reason}`, { step, url: this.page.url() });
    this.exportFailures.push({ id, title, reason });
    return false;
  }

  /** Every download link currently listed on the Transfer History page. */
  async readTransferDownloadUrls() {
    return await this.page.$$eval(
      'a[href*="/transfers/"][href*="/download"]',
      (links) => links.map((a) => a.href),
    );
  }

  /**
   * Snapshot the Transfer History page BEFORE requesting an export.
   *
   * Schoology's Transfer History is a single per-user page that ACCUMULATES every
   * export the account has ever requested. The original implementation waited for
   * `toggles.length >= 3` and then downloaded the first 3 download links on that
   * page. From the second assessment onward at least 3 rows already existed, so
   * the wait returned instantly and the PREVIOUS assessment's CSVs were
   * downloaded and uploaded under the CURRENT assessment's storage key — wrong
   * data, silently, with every log line reporting success.
   *
   * Identifying rows by "what is new since this export was requested" is the only
   * approach that does not depend on page ordering, row count, or filenames.
   */
  async snapshotTransfers() {
    const transfersUrl = `${SCHOOLOGY_URL}/settings/transfers`;
    await this.page.goto(transfersUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
    await sleep(1000);
    return new Set(await this.readTransferDownloadUrls());
  }

  // ── Process ONE assessment (identical to bot's per-assessment loop) ─────
  // Bot flow: snapshot transfers → navigate → export → wait for NEW transfer
  // rows → download only those → upload → next
  async processAssessment(assessment) {
    const { id, path: relPath, title, segments: relSegments } = assessment;
    // Rebind for this assessment: the school+id prefix now appears on every line
    // emitted below, including deep inside the download/upload loops.
    this.log = rootLog.child({ school: this.school.shortName, assessment: id });
    this.log.info("export started", { title, prefix: relPath });

    // Step 0: Record which transfer rows already exist, so the ones this export
    // creates can be told apart from every earlier assessment's.
    const priorTransfers = await this.snapshotTransfers();

    // Step 1: Navigate to assessment results page (bot opens Chrome to this URL)
    await this.page.goto(`${SCHOOLOGY_URL}/assignment/${id}/assessment_results`, {
      waitUntil: "domcontentloaded", timeout: 30000,
    });
    await sleep(2000);

    // Step 2: Click toggle options
    if (!await this.requireClick([
      'span:has-text("Click to toggle options")',
      '.action-links-unfold > span',
    ], { step: "toggle", reason: "results-page options toggle not found (UI change?)",
         id, title, retries: 1, delay: 2000 })) return false;
    await sleep(500);

    // Step 3: Click "Export Stats"
    if (!await this.requireClick([
      'a:has-text("Export Stats")',
      'li.action-export-csv a',
      'a[href*="export_csv"]',
    ], { step: "export-stats", reason: "'Export Stats' link not found (UI change?)",
         id, title, retries: 4, delay: 3000 })) return false;

    // Bot waits 7 seconds here
    await sleep(7000);

    // Step 4: Click "Submitted" filter
    await this.clickElement([
      'span:has-text("Submitted")',
    ], "Submitted filter", { retries: 4, delay: 2000 });
    await sleep(500);

    // Step 5: Click "Next"
    if (!await this.requireClick([
      'input[type="submit"][value="Next"]',
      '#edit-submit',
    ], { step: "next", reason: "'Next' button not found (UI change?)",
         id, title, retries: 1, delay: 2000 })) return false;
    await sleep(1500);

    // Step 6: Check for "no students" error (identical to bot's check)
    const errorDiv = await this.page.$('div:has-text("You must select at least one student to export")');
    if (errorDiv && await errorDiv.isVisible().catch(() => false)) {
      // The one genuinely-correct skip: nothing to export yet. Stays INFO and is
      // NOT recorded as a failure, so it cannot inflate the alert.
      this.log.info("skipped: assessment has no submitted students");
      await this.clickElement(['a:has-text("Cancel")'], "Cancel");
      await this.page.goBack({ waitUntil: "domcontentloaded", timeout: 10000 }).catch(() => {});
      return false;
    }

    // Step 7: Check all 4 export checkboxes (same names as bot)
    for (const name of [
      'input[name="export_submission_summary"]',
      'input[name="export_questions[export_questions]"]',
      'input[name="export_content[export_question_data]"]',
      'input[name="export_content[export_submissions]"]',
    ]) {
      const cb = await this.page.$(name);
      if (cb && !(await cb.isChecked())) await cb.check();
    }

    // Step 8: Click "Export"
    await this.clickElement([
      'input[type="submit"][value="Export"]',
    ], "Export button");

    // Step 9: Click "Transfer History" link (bot clicks this on the results page)
    await sleep(2000);
    await this.clickElement([
      'a:has-text("Transfer History")',
      'a[href*="/settings/transfers"]',
    ], "Transfer History link");
    await sleep(4000); // Bot waits 4 seconds

    // Step 10: Attach to transfers page
    const transfersUrl = `${SCHOOLOGY_URL}/settings/transfers`;
    if (!this.page.url().includes("/settings/transfers")) {
      await this.page.goto(transfersUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
      await sleep(2000);
    }

    // Step 11: Wait for THIS export's transfer rows — i.e. links that were not
    // present in `priorTransfers`. Waiting on a total row count is what caused
    // the cross-assessment corruption (see snapshotTransfers): the page already
    // held rows from every previous export, so the wait ended immediately.
    //
    // Schoology creates one row per ticked checkbox, and the rows do not all
    // appear at once. So: wait until at least the wanted number of new rows
    // exists AND the count has stopped growing, rather than grabbing the first
    // batch that appears mid-write.
    const wantedCount = this.school.downloadIndex.length;
    let freshUrls = [];
    let stableFor = 0;
    for (let attempt = 1; attempt <= 15; attempt++) {
      const current = await this.readTransferDownloadUrls();
      const fresh = current.filter((u) => !priorTransfers.has(u));

      if (fresh.length === freshUrls.length && fresh.length > 0) {
        stableFor++;
      } else {
        stableFor = 0;
      }
      freshUrls = fresh;

      // Settled: enough rows for the wanted files and no new ones last round.
      if (freshUrls.length >= wantedCount && stableFor >= 1) break;

      // DEBUG: fires ~2x per assessment on a healthy run and dominated the log.
      this.log.debug("waiting for this export's transfer rows", {
        attempt: `${attempt}/15`, newRows: freshUrls.length, priorRows: priorTransfers.size,
      });
      await sleep(3000);
      await this.page.reload({ waitUntil: "domcontentloaded", timeout: 15000 });
      await sleep(1000);
    }

    if (freshUrls.length === 0) {
      // Never silently fall back to pre-existing rows — that is precisely the bug.
      // Recorded as a FAILED export, not a skip: a skip means "correctly nothing
      // to do" (no submitted students), whereas this means the export was
      // requested and never materialised. Left as a skip it would be the one
      // total-failure mode the run still reported as green.
      // Include the PRE-EXISTING row count: it distinguishes "Schoology never
      // produced the export" from "the page was already full and we could not tell
      // the new rows apart", which need different responses.
      this.log.error("export produced no new transfer rows — nothing downloaded", null, {
        priorRows: priorTransfers.size, waitedSec: 15 * 4, url: this.page.url(),
      });
      this.exportFailures.push({ id, title, reason: "no new transfer rows within timeout" });
      return false;
    }

    // Step 12: Download every row THIS export created. Four checkboxes are
    // ticked but only three file types are wanted, so download them all and let
    // the prefix filter below decide — never slice by position.
    const downloadUrls = freshUrls;
    const filesToDownload = downloadUrls.length;
    const downloadedFiles = [];

    for (let i = 0; i < filesToDownload; i++) {
      try {
        const [download] = await Promise.all([
          this.page.waitForEvent("download", { timeout: 30000 }),
          this.page.goto(downloadUrls[i], { timeout: 15000 }).catch(() => {}),
        ]);
        const filename = download.suggestedFilename();
        // Prefix local filename with sectionId + gradeName so same assessment in multiple
        // sections doesn't overwrite, and grade is visible in the name.
        // Storage upload keeps the ORIGINAL Schoology filename (never this local rename).
        // Use the canonical class from lib/paths rather than a second, weaker copy
        // (the inline one omitted control chars, trim and the leading-dot guard).
        const gradeTag = assessment.gradeName
          ? safeSegment(assessment.gradeName).replace(/\s+/g, "-")
          : "";
        const prefixParts = [assessment.sectionId, gradeTag].filter(Boolean);
        const localName = prefixParts.length ? `${prefixParts.join("_")}_${filename}` : filename;
        const savePath = path.join(this.downloadDir, localName);
        await download.saveAs(savePath);
        downloadedFiles.push({ path: savePath, filename });
        this.log.debug("downloaded", { file: filename });

        // Go back to transfers for next download
        await this.page.goto(transfersUrl, { waitUntil: "domcontentloaded", timeout: 15000 });
        await sleep(500);
      } catch (err) {
        // Was truncated to 80 chars with no class and no index, so a timeout and a
        // navigation failure were indistinguishable.
        this.log.error("download failed", err, { index: i + 1, of: filesToDownload });
        await this.page.goto(transfersUrl, { waitUntil: "domcontentloaded", timeout: 15000 }).catch(() => {});
      }
    }

    // Step 12b: Keep only the three file types the backend ingests. The export
    // form ticks four boxes, and the backend routes purely on these filename
    // prefixes (file_path_parser.classify_file_type), so anything else is dead
    // weight in a bucket that holds student PII.
    const wanted = downloadedFiles.filter((f) => WANTED_FILE_PREFIXES.some((p) => f.filename.startsWith(p)));
    const discarded = downloadedFiles.length - wanted.length;
    if (discarded > 0) {
      // Name them: if Schoology ever renames its exports, this is the line that
      // says so instead of the triplet silently going missing.
      this.log.warn("ignoring export files with no backend parser", {
        count: discarded,
        files: downloadedFiles.filter((f) => !WANTED_FILE_PREFIXES.some((x) => f.filename.startsWith(x)))
          .map((f) => f.filename).join(", "),
        expectedPrefixes: WANTED_FILE_PREFIXES.join("|"),
      });
    }

    // A partial triplet means the assessment landed incomplete: the backend would
    // ingest question data with no submissions (or vice versa). Report it rather
    // than uploading a half set that looks successful.
    const gotTypes = new Set(
      wanted.map((f) => WANTED_FILE_PREFIXES.find((p) => f.filename.startsWith(p))),
    );
    if (gotTypes.size < WANTED_FILE_PREFIXES.length) {
      const missing = WANTED_FILE_PREFIXES.filter((p) => !gotTypes.has(p));
      this.log.warn("INCOMPLETE export — the backend will ingest a partial triplet", {
        missing: missing.join(", "), got: [...gotTypes].join(", "), prefix: relPath,
      });
      this.incompleteExports.push({ id, title, missing });
    }

    // Step 13: Upload each file to Supabase Storage (immediately after each download).
    // Storage key (frozen contract): <short_name>/<relPath><originalFilename>
    //   relPath = <session>/<category>/<subject>/<grade>/<section>/  (trailing slash)
    // NO %20 encoding — the storage client handles it; use the ORIGINAL Schoology
    // filename (never the local <sectionId>_ rename). Mark uploaded ONLY after the
    // upload resolves without error (success-on-failure fix).
    let uploaded = 0;
    for (const file of wanted) {
      // Route the REAL upload key through the helper so the filename is sanitised
      // too. Building it by hand here was how a "/" in a Schoology-suggested
      // filename could still add a path level and misfile the rows.
      const built = buildRelativeKey({
        session: relSegments.session,
        category: relSegments.category,
        subject: relSegments.subject,
        grade: relSegments.grade,
        section: relSegments.section,
        filename: file.filename,
      });
      for (const w of built.warnings) {
        this.log.warn("storage key sanitised at upload", { detail: w });
      }
      const objectKey = `${this.school.shortName}/${built.key}`;
      try {
        const { error } = await this.supabase.storage
          .from(this.bucket)
          .upload(objectKey, fs.readFileSync(file.path), { contentType: "text/csv", upsert: true });
        if (error) throw error;
        uploaded++;
        this.uploadCount++;
        uploadedKeys.push(objectKey);
        this.log.info("uploaded", { key: objectKey });
      } catch (err) {
        // Counted, not just logged: a run where EVERY upload failed used to end
        // with uploadCount=0, skip the backend trigger, and still exit 0 — a
        // scheduled run would have looked green while shipping nothing.
        this.uploadErrors++;
        // Name the bucket and the storage host: a 403 here is almost always a
        // stale service key or a bucket policy, and neither was previously visible.
        this.log.error("upload failed", err, {
          key: objectKey,
          bucket: this.bucket,
          storageHost: SUPABASE_URL ? new URL(SUPABASE_URL).host : "(unset)",
          status: err.statusCode || err.status,
        });
      }
    }

    this.log.info("export complete", { uploaded, of: wanted.length });
    return uploaded > 0;
  }
}

// ── Per-school worker (one attempt) ──────────────────────────────────────────
// Runs the full discovery → (dry-run report | export → upload → scraper-complete)
// flow for a single school. Returns { uploaded, skipped }. Throws on failure so
// the pool can classify + retry.
async function runSchoolOnce(school, creds, supabase, bucket) {
  const assessments = await discoverAssessments(school, creds);

  if (assessments.length === 0) {
    rootLog.info("nothing to export for this school (not an error)", {
      school: school.shortName,
    });
    return { uploaded: 0, skipped: 0 };
  }

  if (DRY_RUN) {
    log("\nDRY RUN — assessments that would be exported:");
    for (const a of assessments) {
      log(`  [${a.id}] "${a.title}" due:${a.due}`);
      log(`    Course: ${a.courseTitle} - ${a.sectionTitle}`);
      log(`    Key:    ${school.shortName}/${a.path}<filename>.csv`);
    }
    log(`\nTotal: ${assessments.length} assessments`);
    return { uploaded: 0, skipped: 0 };
  }

  // Playwright session — login + process each assessment
  const session = new SchoologySession(school, creds, supabase, bucket);
  let successCount = 0;
  let skipCount = 0;
  try {
    await session.init();
    await session.login();

    for (let i = 0; i < assessments.length; i++) {
      rootLog.debug("assessment progress", {
        school: school.shortName, index: `${i + 1}/${assessments.length}`,
      });
      const ok = await session.processAssessment(assessments[i]);
      if (ok) successCount++;
      else skipCount++;

      // Small delay between assessments
      if (i < assessments.length - 1) await sleep(1000);
    }
    rootLog.info("school complete", {
      school: school.shortName,
      exported: successCount, skipped: skipCount, total: assessments.length,
      filesUploaded: session.uploadCount,
      uploadErrors: session.uploadErrors || undefined,
      exportFailures: session.exportFailures.length || undefined,
    });
  } catch (err) {
    // Capture a debug screenshot, then rethrow so the pool classifies + retries.
    // Log the path: the screenshot was always taken and never mentioned, so an
    // operator had no idea an artefact existed.
    const shotPath = await session.screenshot(`fatal-${school.shortName}`).catch(() => null);
    if (shotPath) rootLog.warn("debug screenshot saved", { path: shotPath, school: school.shortName });
    throw err;
  } finally {
    await session.close();
  }

  // Notify backend that this school's uploads are done (replaces Success.txt).
  // Only fire if at least one file made it to storage. A scraper-complete failure
  // (after retries) marks the school failed — the uploads are live and the run
  // can be re-triggered.
  if (session.uploadCount > 0) {
    const body = await postScraperComplete(school.shortName);
    rootLog.info("backend ingestion triggered", {
      school: school.shortName, response: body.substring(0, 200),
    });
  } else {
    rootLog.warn("no files reached storage — backend NOT triggered", {
      school: school.shortName,
    });
  }

  // Discovery found work but NOTHING reached storage → this is a failure, not a
  // quiet no-op. Previously uploadCount=0 skipped the trigger, returned normally,
  // and the process exited 0, so an all-uploads-failed run (bad service key,
  // revoked bucket access, disk full) looked identical to a clean run with
  // nothing to do.
  if (session.uploadErrors > 0 && session.uploadCount === 0) {
    throw new Error(
      `all uploads failed for ${school.name} `
      + `(${session.uploadErrors} error(s), 0 files in storage)`,
    );
  }

  return {
    uploaded: session.uploadCount,
    exported: successCount,
    skipped: skipCount,
    uploadErrors: session.uploadErrors,
    incompleteExports: session.incompleteExports,
    exportFailures: session.exportFailures,
  };
}

// Run one school with credential resolution, transient retry, and failure
// isolation. Never throws — returns a ledger entry describing the outcome.
async function runSchoolIsolated(school, supabase, bucket) {
  const ledger = {
    school: school.name,
    shortName: school.shortName,
    status: "failed",
    uploaded: 0,
    skipped: 0,
    error: null,
    errorClass: null,
  };

  // Credential resolution failures are fatal for the school (F16), never retried.
  let creds;
  try {
    creds = resolveCredentials(school);
    rootLog.info("credentials resolved", { school: school.shortName, source: creds.source });
  } catch (err) {
    ledger.status = "failed";
    ledger.error = err.message;
    ledger.errorClass = "credential";
    rootLog.error("credential resolution FAILED — school skipped, no retry", err, {
      school: school.shortName,
    });
    return ledger;
  }

  for (let attempt = 0; attempt <= TRANSIENT_RETRY_ATTEMPTS; attempt++) {
    try {
      const result = await runSchoolOnce(school, creds, supabase, bucket);
      ledger.status = "ok";
      ledger.uploaded = result.uploaded;
      ledger.exported = result.exported;
      ledger.skipped = result.skipped;
      // Partial failures: the school completed, but some files did not land.
      // Surfaced separately from status so the batch can exit non-zero without
      // pretending the whole school failed.
      ledger.uploadErrors = result.uploadErrors || 0;
      ledger.incompleteExports = result.incompleteExports || [];
      ledger.exportFailures = result.exportFailures || [];
      ledger.error = null;
      ledger.errorClass = null;
      return ledger;
    } catch (err) {
      const errorClass = classifyError(err);
      ledger.status = "failed";
      ledger.error = (err.message || String(err)).substring(0, 300);
      ledger.errorClass = errorClass;

      // Credential rejection is fatal — never retry.
      if (errorClass === "credential") {
        rootLog.error("Schoology rejected the credentials — school skipped, no retry", err, {
          school: school.shortName,
        });
        return ledger;
      }

      // Transient — one retry with backoff, then give up.
      if (attempt < TRANSIENT_RETRY_ATTEMPTS) {
        rootLog.warn("school failed (transient) — retrying", {
          school: school.shortName, backoffSec: TRANSIENT_RETRY_BACKOFF_MS / 1000,
          errClass: ledger.errorClass, errMsg: ledger.error,
        });
        await sleep(TRANSIENT_RETRY_BACKOFF_MS);
        continue;
      }
      rootLog.error("school FAILED after all retries", err, { school: school.shortName });
      return ledger;
    }
  }

  return ledger;
}

// Hand-rolled bounded worker pool (no new dependency). Processes `items` through
// `worker`, at most `limit` in flight at once, preserving per-item isolation.
async function runPool(items, limit, worker) {
  const results = new Array(items.length);
  let cursor = 0;

  async function drain() {
    while (true) {
      const idx = cursor++;
      if (idx >= items.length) return;
      results[idx] = await worker(items[idx], idx);
    }
  }

  const runners = [];
  const width = Math.min(limit, items.length);
  for (let i = 0; i < width; i++) runners.push(drain());
  await Promise.all(runners);
  return results;
}

// ── Main ────────────────────────────────────────────────────────────────────
async function _runMain(summary) {
  const startTime = Date.now();
  // Startup config echo. The old banner printed three rules and no configuration,
  // so "this run wrote to the wrong environment" was undiagnosable after the fact:
  // nothing in the log said which backend, which Supabase project, or which
  // credential identity was used. Values are host-only / lengths — never secrets.
  rootLog.info("scraper starting", {
    mode: DRY_RUN ? "dry-run" : "live",
    backend: BACKEND_BASE_URL,
    schoologyUrl: SCHOOLOGY_URL,
    storageHost: SUPABASE_URL ? new URL(SUPABASE_URL).host : "(unset)",
    concurrency: SCRAPER_CONCURRENCY,
    triggerSecret: INGESTION_TRIGGER_SECRET ? `set(${INGESTION_TRIGGER_SECRET.length})` : "MISSING",
    logLevel: process.env.SCRAPER_LOG_LEVEL || "info",
    node: process.version,
  });

  if (!INGESTION_TRIGGER_SECRET) {
    rootLog.warn("INGESTION_TRIGGER_SECRET is not set — every backend call will be rejected with 401");
  }

  // Fetch config from the backend (replaces schools.json).
  let config;
  try {
    config = await fetchScraperConfig();
  } catch (err) {
    rootLog.error("FATAL: could not fetch scraper config from the backend", err, {
      backend: BACKEND_BASE_URL,
    });
    summary.fatalError = { name: err.name || "Error", message: err.message || String(err) };
    process.exitCode = 1;
    return;
  }

  const bucket = config?.storage?.bucket;
  if (!bucket) {
    rootLog.error("FATAL: scraper-config response did not include storage.bucket");
    summary.fatalError = { name: "ConfigError", message: "scraper-config did not include storage.bucket" };
    process.exitCode = 1;
    return;
  }
  summary.bucket = bucket;

  // Normalize backend school payload → the shape discovery/export expect.
  // credential_ref is optional (contract v1.1, additive) — absent-tolerant.
  let schools = (config.schools || []).map((s) => ({
    schoolId: s.school_id,
    name: s.name,
    shortName: s.short_name,
    buildingId: s.schoology_building_id,
    gradingCategoryRegex: s.category_regex,
    dueDateWindowDays: s.due_date_window_days,
    coursePageLimit: s.course_page_limit,
    downloadIndex: s.download_index || [1, 2, 3],
    categoryFolderOverride: s.category_folder_override,
    currentSession: s.current_session,
    timezone: s.timezone,
    credentialRef: s.credential_ref || null,
  }));

  // Filter schools (partial, case-insensitive name match — same as bot).
  if (SCHOOL_FILTER) {
    schools = schools.filter((s) => (s.name || "").toLowerCase().includes(SCHOOL_FILTER.toLowerCase()));
    if (schools.length === 0) {
      rootLog.error(`FATAL: no active school matches --school "${SCHOOL_FILTER}"`, null, {
        available: (config.schools || []).map((x) => x.short_name).join(", ") || "(none)",
      });
      summary.fatalError = {
        name: "NoSuchSchool",
        message: `no active school matches --school "${SCHOOL_FILTER}"`,
      };
      process.exitCode = 1;
      return;
    }
  }
  rootLog.info("schools selected", {
    count: schools.length,
    schools: schools.map((x) => x.shortName).join(", "),
  });

  // Two schools that resolve to the SAME Schoology identity must never run
  // concurrently. Schoology's Transfer History is one page per ACCOUNT, so
  // parallel exports on a shared identity interleave and each run can download
  // the other's CSVs — the same class of bug as the within-run race, but across
  // schools and invisible to the snapshot-diff fix.
  const identityOf = (school) => {
    try {
      return resolveCredentials(school).source;
    } catch {
      return `unresolved:${school.shortName}`;
    }
  };
  const identityGroups = new Map();
  for (const sc of schools) {
    const id = identityOf(sc);
    if (!identityGroups.has(id)) identityGroups.set(id, []);
    identityGroups.get(id).push(sc);
  }
  const shared = [...identityGroups.entries()].filter(([, g]) => g.length > 1);
  for (const [id, group] of shared) {
    rootLog.warn(
      "multiple schools share one Schoology identity — they will run SEQUENTIALLY "
      + "because Transfer History is per-account",
      { identity: id, schools: group.map((x) => x.shortName).join(", ") },
    );
  }
  const effectiveConcurrency = Math.min(SCRAPER_CONCURRENCY, identityGroups.size || 1);
  rootLog.info("concurrency resolved", {
    requested: SCRAPER_CONCURRENCY,
    effective: effectiveConcurrency,
    distinctIdentities: identityGroups.size,
  });

  // Supabase Storage client (service-role key bypasses Storage RLS, matching backend).
  // Not needed for --dry-run (no uploads). Shared across schools (stateless client).
  let supabase = null;
  if (!DRY_RUN) {
    if (!SUPABASE_URL || !SUPABASE_SERVICE_KEY) {
      // Was routed through the info-level shim, so a FATAL misconfiguration went to
      // stdout at INFO — defeating the reason the logger splits streams at all.
      rootLog.error("FATAL: SUPABASE_URL and SUPABASE_SERVICE_KEY are required for upload (omit with --dry-run).");
      process.exitCode = 1;
      return;
    }
    supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY, { auth: { persistSession: false } });
  }

  // Bounded-concurrency pool over schools; each school is fully isolated.
  // Parallelise across identities, serialise within one. A group is a list of
  // schools sharing a Schoology account; those must not overlap in time.
  const groupResults = await runPool(
    [...identityGroups.values()],
    effectiveConcurrency,
    async (group) => {
      const out = [];
      for (const school of group) {
        out.push(await runSchoolIsolated(school, supabase, bucket));
      }
      return out;
    },
  );
  const ledger = groupResults.flat();

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

  // Fold discovery stats into the ledger so the summary + email can report the
  // funnel per school without re-deriving anything.
  for (const r of ledger) {
    const stats = discoveryStats.get(r.shortName);
    if (stats) {
      r.discovered = stats.discovered;
      r.keyWarnings = stats.keyWarnings;
      r.funnel = stats.funnel;
    }
  }
  summary.schools = ledger;
  summary.durationSec = elapsed;

  // Final batch summary.
  // Report the concurrency actually used. Recomputing it from the school count
   // overstated parallelism whenever schools were serialised by shared identity.
  log(`  BATCH SUMMARY (${elapsed}s, concurrency ${effectiveConcurrency})`);
  let failedCount = 0;
  let partialCount = 0;
  for (const r of ledger) {
    if (r.status === "ok") {
      const errs = r.uploadErrors || 0;
      const incomplete = (r.incompleteExports || []).length;
      const exportFails = (r.exportFailures || []).length;
      if (errs > 0 || incomplete > 0 || exportFails > 0) partialCount++;
      log(`  ${errs || incomplete || exportFails ? "PARTIAL " : "OK      "} ${r.school}: `
        + `uploaded=${r.uploaded} skipped=${r.skipped}`
        + `${errs ? ` uploadErrors=${errs}` : ""}`
        + `${incomplete ? ` incompleteExports=${incomplete}` : ""}`
        + `${exportFails ? ` exportFailures=${exportFails}` : ""}`);
      for (const ef of r.exportFailures || []) {
        log(`             ! ${ef.id} "${ef.title}" export failed: ${ef.reason}`);
      }
      for (const inc of r.incompleteExports || []) {
        log(`             ! ${inc.id} "${inc.title}" missing: ${inc.missing.join(", ")}`);
      }
    } else {
      failedCount++;
      log(`  FAILED   ${r.school}: [${r.errorClass}] ${r.error}`);
    }
  }
  // One authority on "did this run succeed": lib/notify.js::overallStatus. This
  // used to be a second, weaker implementation (no FATAL, no NO-DATA arm), so the
  // logged verdict, the email subject and the exit code could disagree.
  const verdict = overallStatus(summary);
  const emit = (verdict === "OK" || verdict === "NO-DATA")
    ? rootLog.info.bind(rootLog) : rootLog.warn.bind(rootLog);
  emit(`run finished: ${verdict}`, {
    schools: ledger.length,
    ok: ledger.length - failedCount - partialCount,
    partial: partialCount,
    failed: failedCount,
    filesUploaded: uploadedKeys.length,
    durationSec: elapsed,
  });

  // Any failed school → non-zero exit (F17). One failure never aborts the batch.
  // A PARTIAL school also exits non-zero: a scheduled run that silently shipped
  // an incomplete triplet is the failure mode most likely to go unnoticed, since
  // the data looks present until someone reads a report.
  if (verdict !== "OK" && verdict !== "NO-DATA") process.exitCode = 1;
}

/**
 * main() = the run, plus a guaranteed notification.
 *
 * The email is sent from a `finally`, so it goes out on the success path, on a
 * fatal abort (config unreachable, missing bucket, unknown school) AND on an
 * unexpected throw. That ordering matters: the scraper's most likely failures are
 * the ones where the backend is unreachable, which is exactly when nobody would
 * otherwise learn the run died.
 *
 * A notification failure never changes the run's exit code — sendRunSummary
 * swallows and logs its own errors.
 */
async function main() {
  const summary = {
    runId: RUN_ID,
    startedAt: new Date().toISOString(),
    dryRun: DRY_RUN,
    schoolFilter: SCHOOL_FILTER,
    assessmentFilter: ASSESSMENT_FILTER,
    backendBaseUrl: BACKEND_BASE_URL,
    supabaseHost: SUPABASE_URL ? new URL(SUPABASE_URL).host : "(unset)",
    bucket: "(unknown)",
    durationSec: "0",
    schools: [],
    storageKeys: [],
    fatalError: null,
  };

  try {
    await _runMain(summary);
  } catch (err) {
    rootLog.error("FATAL: unhandled error — the run did not complete", err);
    summary.fatalError = { name: err.name || "Error", message: err.message || String(err) };
    process.exitCode = 1;
  } finally {
    summary.storageKeys = uploadedKeys;
    await sendRunSummary(summary, { log: rootLog });
  }
}

// Requiring this file must never start a scrape (the pure helpers it used to hold
// now live in ./lib and are tested there).
if (require.main === module) {
  // main() was previously called bare: an async throw became an unhandled
  // rejection, which Node reports on stderr but (depending on version/flags) can
  // still exit 0 — a scheduled run would look green after crashing.
  main().catch((err) => {
    console.error(`FATAL: ${err && err.stack ? err.stack : err}`);
    process.exit(1);
  });
}
