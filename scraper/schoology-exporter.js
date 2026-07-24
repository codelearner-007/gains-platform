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
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const https = require("https");
const { createClient } = require("@supabase/supabase-js");
require("dotenv").config();

// ── CLI flags ────────────────────────────────────────────────────────────────
const HEADED = process.argv.includes("--headed");
const DRY_RUN = process.argv.includes("--dry-run");
const SCHOOL_FILTER = process.argv.includes("--school")
  ? process.argv[process.argv.indexOf("--school") + 1]
  : null;

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

// ── Helpers ─────────────────────────────────────────────────────────────────
function ensureDir(dir) { if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true }); }
function log(msg) { console.log(`[${new Date().toISOString().substring(11, 19)}] ${msg}`); }
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

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
function apiGet(creds, endpoint) {
  const key = creds && creds.consumerKey;
  const secret = creds && creds.consumerSecret;
  if (!key || !secret) return Promise.resolve(null);

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
        let loc = res.headers.location;
        if (loc.startsWith("http")) loc = new URL(loc).pathname;
        resolve(apiGet(creds, loc.replace(/^\/v1/, "")));
        return;
      }
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => { try { resolve(res.statusCode === 200 ? JSON.parse(body) : null); } catch { resolve(null); } });
    });
    req.on("error", () => resolve(null));
    req.setTimeout(15000, () => { req.destroy(); resolve(null); });
    req.end();
  });
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
  log("DISCOVERY: Fetching assessments (matching production C# logic)...");

  // Production: var currentDate = DateTime.UtcNow;
  const currentDate = new Date();
  // Production: var thresholdDate = currentDate.AddDays(-14);
  const thresholdDate = new Date(currentDate.getTime() - school.dueDateWindowDays * 24 * 60 * 60 * 1000);
  // Production: var academicYear = currentDate.Month >= 8 ? ... : ...
  const month1Based = currentDate.getMonth() + 1; // JS months are 0-based
  const computedAcademicYear = month1Based >= 8
    ? `${currentDate.getFullYear()}-${String((currentDate.getFullYear() + 1) % 100).padStart(2, "0")}`
    : `${currentDate.getFullYear() - 1}-${String(currentDate.getFullYear() % 100).padStart(2, "0")}`;

  // session segment = school.current_session override || computed academic year
  const session = school.currentSession || computedAcademicYear;

  log(`  Session: ${session} (computed: ${computedAcademicYear})`);
  log(`  Threshold: ${thresholdDate.toISOString().substring(0, 10)} to ${currentDate.toISOString().substring(0, 10)}`);

  // Production: categoryRegex from tenant config "LessonAssessments"
  // e.g. "(Chapter|lesson|Weekly|Module|Assessments)"
  const categoryRegex = new RegExp(school.gradingCategoryRegex, "i");
  log(`  Category regex: ${school.gradingCategoryRegex}`);

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
  const coursePageLimit = school.coursePageLimit || 200;

  // Step 1: Paginate through courses
  // Production uses per-school API keys so only gets that school's courses.
  // We use a shared admin key, so filter by building_id to scope to one school.
  let allCourses = [];
  const buildingFilter = school.buildingId ? `&building_id=${school.buildingId}` : "";
  let nextCourseUrl = `/courses?start_id=0&limit=${coursePageLimit}${buildingFilter}`;
  let firstCoursePage = true;
  while (nextCourseUrl) {
    const data = await apiGet(creds, nextCourseUrl);
    // A null first page means the credentials were rejected (401/redirect loop):
    // fail LOUDLY as a credential error rather than silently return 0 assessments.
    if (firstCoursePage && data === null) {
      throw new CredentialError(
        `Schoology API rejected credentials (${creds.source}) for "${school.name}" — no courses returned`,
      );
    }
    firstCoursePage = false;
    if (!data?.course?.length) break;
    allCourses = allCourses.concat(data.course);
    nextCourseUrl = data.links?.next || null;
    if (nextCourseUrl) {
      if (nextCourseUrl.startsWith("http")) {
        const parsed = new URL(nextCourseUrl);
        nextCourseUrl = parsed.pathname.replace("/v1", "") + parsed.search;
      }
    }
  }
  log(`  Courses: ${allCourses.length}`);

  const assignmentUrls = new Map(); // key "{id}:{path}" (same dedup as Set), value: metadata

  for (const course of allCourses) {
    // Production: check if (subject_area, grade_level) combo is valid
    const subjectArea = course.subject_area ?? -1;
    const gradeLevel = course.grade_level_range_start ?? -1;
    const comboKey = `${subjectArea}-${gradeLevel}`;
    if (!validComboSet.has(comboKey)) continue;

    const subjectName = SUBJECT_CODE_MAP[subjectArea] || "Other";
    const gradeName = GRADE_CODE_MAP[gradeLevel] || "No grade level/remove grade level";

    const courseId = course.id;

    // Step 2: Get sections for this course
    const sectionsData = await apiGet(creds, `/courses/${courseId}/sections`);
    if (!sectionsData?.section?.length) continue;

    for (const section of sectionsData.section) {
      const sectionId = section.id;
      // Production: sectionName from section_code, fallback to section_title
      const sectionCode = section.section_code;
      const sectionTitle = section.section_title || "Unknown Section";
      const rawSectionName = sectionCode && sectionCode.trim() ? sectionCode : sectionTitle;
      const sectionName = `Sec ${rawSectionName.replace(/[<>:"/\\|?*]/g, "_")}`;

      // Step 3: Get grading categories
      const catsData = await apiGet(creds, `/sections/${sectionId}/grading_categories`);
      const gradingCategories = catsData?.grading_category || [];

      // Production: build category map {id → title}
      const gradingCategoryMap = {};
      for (const gc of gradingCategories) {
        if (gc.id && gc.title) gradingCategoryMap[String(gc.id)] = gc.title;
      }

      // Production: check if ANY category title matches the regex
      const matchingCategories = gradingCategories.filter((gc) => categoryRegex.test(gc.title || ""));
      if (matchingCategories.length === 0) continue;

      // Step 4: Paginate through assignments (production uses /assignments, not /grade_items)
      let nextAssignmentUrl = `/sections/${sectionId}/assignments?start=0&limit=${coursePageLimit}`;
      while (nextAssignmentUrl) {
        const assignmentsData = await apiGet(creds, nextAssignmentUrl);
        if (!assignmentsData?.assignment?.length) break;

        // Production filter: type=assessment AND category title matches regex
        const validAssignments = assignmentsData.assignment.filter((a) => {
          if (a.type !== "assessment") return false;
          const catId = String(a.grading_category || "");
          if (!gradingCategoryMap[catId]) return false;
          return categoryRegex.test(gradingCategoryMap[catId]);
        });

        for (const assignment of validAssignments) {
          const dueDateStr = assignment.due;
          if (!dueDateStr) continue;

          // Production: parse due date, strip time, convert midnight EST → UTC, compare date-only
          const parsedDue = new Date(dueDateStr);
          if (isNaN(parsedDue.getTime())) continue;

          // Strip time (date only) — production: dueDate.Date
          const dueDateOnly = new Date(parsedDue.getFullYear(), parsedDue.getMonth(), parsedDue.getDate());

          // Convert midnight EST to UTC — production: TimeZoneInfo.ConvertTimeToUtc(dueDateDateOnly, easternZone)
          // EST is UTC-5, EDT is UTC-4. Approximate: add 5 hours (EST)
          const dueDateUtc = new Date(dueDateOnly.getTime() + 5 * 60 * 60 * 1000);

          // Compare date portions only — production: dueDateUtc.Date < thresholdDate.Date
          const dueDay = dueDateUtc.toISOString().substring(0, 10);
          const thresholdDay = thresholdDate.toISOString().substring(0, 10);
          const currentDay = currentDate.toISOString().substring(0, 10);

          if (dueDay < thresholdDay || dueDay > currentDay) continue;

          // Production: get assignmentId from web_url
          const webUrl = assignment.web_url || "";
          const assignmentId = webUrl.split("/").pop();
          if (!assignmentId || !/^\d+$/.test(assignmentId)) continue;

          // Category folder: per-school override (preserves the two-space literal
          // "1 - Lesson  Assessments") else the live grading-category title.
          const gradingCategoryId = String(assignment.grading_category || "");
          const categoryFolder = school.categoryFolderOverride || gradingCategoryMap[gradingCategoryId] || "Unknown Category";

          // Production: formatted = "{assignmentId}:{session}/{category}/{subjectName}/{gradeName}/{sectionName}/"
          const formatted = `${assignmentId}:${session}/${categoryFolder}/${subjectName}/${gradeName}/${sectionName}/`;
          if (!assignmentUrls.has(formatted)) {
            assignmentUrls.set(formatted, {
              title: assignment.title || "",
              due: assignment.due || "",
              courseTitle: course.title || "",
              sectionId: String(sectionId),
              sectionTitle,
              gradeName,
            });
          }
        }

        // Pagination
        nextAssignmentUrl = assignmentsData.links?.next || null;
        if (nextAssignmentUrl && nextAssignmentUrl.startsWith("http")) {
          nextAssignmentUrl = new URL(nextAssignmentUrl).pathname.replace("/v1", "") + "?" + new URL(nextAssignmentUrl).search.substring(1);
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
      title: meta.title,
      sectionId: meta.sectionId,
      sectionTitle: meta.sectionTitle,
      courseTitle: meta.courseTitle,
      due: meta.due,
      gradeName: meta.gradeName,
    });
  }

  log(`  Assessments matching all filters: ${assessments.length}`);
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
  }

  async init() {
    ensureDir(DOWNLOAD_DIR);
    ensureDir(SCREENSHOT_DIR);
    this.browser = await chromium.launch({ headless: !HEADED, slowMo: HEADED ? 150 : 0 });
    this.context = await this.browser.newContext({ viewport: { width: 1920, height: 1080 }, acceptDownloads: true });
    this.page = await this.context.newPage();
    this.page.setDefaultTimeout(20000);
  }

  async close() { if (this.browser) await this.browser.close(); }

  async screenshot(name) {
    try { await this.page.screenshot({ path: path.join(SCREENSHOT_DIR, `${name}.png`), fullPage: false }); }
    catch { /* swallow like the bot */ }
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
    log("LOGIN: Opening Schoology...");
    await this.page.goto(SCHOOLOGY_URL, { waitUntil: "domcontentloaded", timeout: 30000 });
    await sleep(2000);

    if (this.page.url().includes("/home") || this.page.url().includes("/courses")) {
      log("  Already logged in");
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
    log("  Login successful");
  }

  // ── Process ONE assessment (identical to bot's per-assessment loop) ─────
  // Bot flow: navigate → export → go to transfers → download 3 → upload 3 → next
  async processAssessment(assessment) {
    const { id, path: relPath, title } = assessment;
    log(`EXPORT: ${id} "${title}"`);

    // Step 1: Navigate to assessment results page (bot opens Chrome to this URL)
    await this.page.goto(`${SCHOOLOGY_URL}/assignment/${id}/assessment_results`, {
      waitUntil: "domcontentloaded", timeout: 30000,
    });
    await sleep(2000);

    // Step 2: Click toggle options
    const toggleOk = await this.clickElement([
      'span:has-text("Click to toggle options")',
      '.action-links-unfold > span',
    ], "toggle", { retries: 1, delay: 2000 });
    if (!toggleOk) { log(`  SKIP: no toggle found`); return false; }
    await sleep(500);

    // Step 3: Click "Export Stats"
    const exportOk = await this.clickElement([
      'a:has-text("Export Stats")',
      'li.action-export-csv a',
      'a[href*="export_csv"]',
    ], "Export Stats", { retries: 4, delay: 3000 });
    if (!exportOk) { log(`  SKIP: no Export Stats link`); return false; }

    // Bot waits 7 seconds here
    await sleep(7000);

    // Step 4: Click "Submitted" filter
    await this.clickElement([
      'span:has-text("Submitted")',
    ], "Submitted filter", { retries: 4, delay: 2000 });
    await sleep(500);

    // Step 5: Click "Next"
    const nextOk = await this.clickElement([
      'input[type="submit"][value="Next"]',
      '#edit-submit',
    ], "Next button", { retries: 1, delay: 2000 });
    if (!nextOk) { log(`  SKIP: no Next button`); return false; }
    await sleep(1500);

    // Step 6: Check for "no students" error (identical to bot's check)
    const errorDiv = await this.page.$('div:has-text("You must select at least one student to export")');
    if (errorDiv && await errorDiv.isVisible().catch(() => false)) {
      log(`  SKIP: no submitted students`);
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

    // Step 11: Wait for transfer items to appear (bot loops 15 times with F5 refresh)
    for (let attempt = 1; attempt <= 15; attempt++) {
      const toggles = await this.page.$$('span:has-text("Click to toggle options")');
      if (toggles.length >= this.school.downloadIndex.length) {
        break;
      }
      log(`  Waiting for exports... attempt ${attempt}/15`);
      await sleep(3000);
      await this.page.reload({ waitUntil: "domcontentloaded", timeout: 15000 });
      await sleep(1000);
    }

    // Step 12: Download loop — for each DownloadIndex (1,2,3)
    // Bot downloads files one at a time using direct download URLs
    const downloadUrls = await this.page.$$eval(
      'a[href*="/transfers/"][href*="/download"]',
      (links) => links.map((a) => a.href)
    );

    const filesToDownload = Math.min(this.school.downloadIndex.length, downloadUrls.length);
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
        const gradeTag = assessment.gradeName
          ? assessment.gradeName.replace(/[<>:"/\\|?*]/g, "_").replace(/\s+/g, "-")
          : "";
        const prefixParts = [assessment.sectionId, gradeTag].filter(Boolean);
        const localName = prefixParts.length ? `${prefixParts.join("_")}_${filename}` : filename;
        const savePath = path.join(DOWNLOAD_DIR, localName);
        await download.saveAs(savePath);
        downloadedFiles.push({ path: savePath, filename });
        log(`  Downloaded: ${localName}`);

        // Go back to transfers for next download
        await this.page.goto(transfersUrl, { waitUntil: "domcontentloaded", timeout: 15000 });
        await sleep(500);
      } catch (err) {
        log(`  Download error: ${err.message.substring(0, 80)}`);
        await this.page.goto(transfersUrl, { waitUntil: "domcontentloaded", timeout: 15000 }).catch(() => {});
      }
    }

    // Step 13: Upload each file to Supabase Storage (immediately after each download).
    // Storage key (frozen contract): <short_name>/<relPath><originalFilename>
    //   relPath = <session>/<category>/<subject>/<grade>/<section>/  (trailing slash)
    // NO %20 encoding — the storage client handles it; use the ORIGINAL Schoology
    // filename (never the local <sectionId>_ rename). Mark uploaded ONLY after the
    // upload resolves without error (success-on-failure fix).
    let uploaded = 0;
    for (const file of downloadedFiles) {
      const objectKey = `${this.school.shortName}/${relPath}${file.filename}`;
      try {
        const { error } = await this.supabase.storage
          .from(this.bucket)
          .upload(objectKey, fs.readFileSync(file.path), { contentType: "text/csv", upsert: true });
        if (error) throw error;
        uploaded++;
        this.uploadCount++;
        log(`  Uploaded: ${objectKey}`);
      } catch (err) {
        log(`  Upload failed: ${(err.message || String(err)).substring(0, 120)}`);
      }
    }

    log(`  Done: ${uploaded}/${downloadedFiles.length} files uploaded for ${id}`);
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
    log(`No assessments to export for ${school.name}.`);
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
      log(`\n[${school.name} ${i + 1}/${assessments.length}] ──────────────────`);
      const ok = await session.processAssessment(assessments[i]);
      if (ok) successCount++;
      else skipCount++;

      // Small delay between assessments
      if (i < assessments.length - 1) await sleep(1000);
    }

    log(`\n================================================================`);
    log(`  COMPLETE: ${school.name}`);
    log(`  Exported: ${successCount} | Skipped: ${skipCount} | Total: ${assessments.length}`);
    log(`  Files uploaded: ${session.uploadCount}`);
    log(`================================================================`);
  } catch (err) {
    // Capture a debug screenshot, then rethrow so the pool classifies + retries.
    await session.screenshot(`fatal-${school.shortName}`).catch(() => {});
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
    log(`  scraper-complete OK for ${school.name}: ${body.substring(0, 200)}`);
  } else {
    log(`  No files uploaded for ${school.name} — skipping scraper-complete.`);
  }

  return { uploaded: session.uploadCount, skipped: skipCount };
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
    log(`  Credentials for ${school.name}: ${creds.source}`);
  } catch (err) {
    ledger.status = "failed";
    ledger.error = err.message;
    ledger.errorClass = "credential";
    log(`  CREDENTIAL FAILURE for ${school.name}: ${err.message}`);
    return ledger;
  }

  for (let attempt = 0; attempt <= TRANSIENT_RETRY_ATTEMPTS; attempt++) {
    try {
      const result = await runSchoolOnce(school, creds, supabase, bucket);
      ledger.status = "ok";
      ledger.uploaded = result.uploaded;
      ledger.skipped = result.skipped;
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
        log(`  CREDENTIAL FAILURE for ${school.name}: ${ledger.error}`);
        return ledger;
      }

      // Transient — one retry with backoff, then give up.
      if (attempt < TRANSIENT_RETRY_ATTEMPTS) {
        log(`  ${school.name} failed (transient): ${ledger.error} — retrying in ${TRANSIENT_RETRY_BACKOFF_MS / 1000}s`);
        await sleep(TRANSIENT_RETRY_BACKOFF_MS);
        continue;
      }
      log(`  ${school.name} failed after retries: ${ledger.error}`);
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
async function main() {
  const startTime = Date.now();
  log("================================================================");
  log("  SCHOOLOGY ASSESSMENT EXPORTER");
  log("================================================================");

  if (!INGESTION_TRIGGER_SECRET) {
    log("WARN: INGESTION_TRIGGER_SECRET is not set — backend calls will be rejected (401).");
  }

  // Fetch config from the backend (replaces schools.json).
  let config;
  try {
    config = await fetchScraperConfig();
  } catch (err) {
    log(`FATAL: could not fetch scraper config: ${err.message}`);
    process.exitCode = 1;
    return;
  }

  const bucket = config?.storage?.bucket;
  if (!bucket) {
    log("FATAL: scraper-config did not include storage.bucket");
    process.exitCode = 1;
    return;
  }

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
      log(`No school matching "${SCHOOL_FILTER}" found in scraper-config`);
      return;
    }
  }
  log(`Schools to process: ${schools.map((s) => s.name).join(", ")}`);
  log(`Concurrency: ${Math.min(SCRAPER_CONCURRENCY, schools.length || 1)} (SCRAPER_CONCURRENCY=${SCRAPER_CONCURRENCY})`);

  // Supabase Storage client (service-role key bypasses Storage RLS, matching backend).
  // Not needed for --dry-run (no uploads). Shared across schools (stateless client).
  let supabase = null;
  if (!DRY_RUN) {
    if (!SUPABASE_URL || !SUPABASE_SERVICE_KEY) {
      log("FATAL: SUPABASE_URL and SUPABASE_SERVICE_KEY are required for upload (omit with --dry-run).");
      process.exitCode = 1;
      return;
    }
    supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY, { auth: { persistSession: false } });
  }

  // Bounded-concurrency pool over schools; each school is fully isolated.
  const ledger = await runPool(schools, SCRAPER_CONCURRENCY, (school) =>
    runSchoolIsolated(school, supabase, bucket),
  );

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

  // Final batch summary.
  log(`\n================================================================`);
  log(`  BATCH SUMMARY (${elapsed}s, concurrency ${Math.min(SCRAPER_CONCURRENCY, schools.length || 1)})`);
  log(`================================================================`);
  let failedCount = 0;
  for (const r of ledger) {
    if (r.status === "ok") {
      log(`  OK       ${r.school}: uploaded=${r.uploaded} skipped=${r.skipped}`);
    } else {
      failedCount++;
      log(`  FAILED   ${r.school}: [${r.errorClass}] ${r.error}`);
    }
  }
  log(`  Schools: ${ledger.length} | OK: ${ledger.length - failedCount} | Failed: ${failedCount}`);
  log(`================================================================`);

  // Any failed school → non-zero exit (F17). One failure never aborts the batch.
  if (failedCount > 0) process.exitCode = 1;
}

main();
