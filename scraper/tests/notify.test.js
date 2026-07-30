/**
 * Run-summary email tests (node --test).
 *
 * Two properties matter most and are asserted hardest:
 *   1. Sending mail NEVER changes the outcome of a run — no throw escapes.
 *   2. A misconfiguration that would silently suppress alerts is LOUD.
 */
const test = require("node:test");
const assert = require("node:assert/strict");

const {
  parseRecipients, invalidRecipients, overallStatus, buildSubject, buildBody, sendRunSummary,
} = require("../lib/notify.js");

function collectLog() {
  const lines = { info: [], warn: [], error: [] };
  return {
    lines,
    info: (m, f) => lines.info.push(m + JSON.stringify(f || {})),
    warn: (m, f) => lines.warn.push(m + JSON.stringify(f || {})),
    error: (m, e, f) => lines.error.push(m + JSON.stringify(f || {})),
    debug() {},
  };
}

const baseSummary = (over = {}) => ({
  runId: "abc123",
  startedAt: "2026-07-30T07:00:00.000Z",
  durationSec: "42.0",
  dryRun: false,
  schoolFilter: "Athenian",
  assessmentFilter: null,
  backendBaseUrl: "https://backend.example",
  supabaseHost: "db.example",
  bucket: "schoology-ingest",
  storageKeys: [],
  fatalError: null,
  schools: [{ school: "Athenian", shortName: "Athenian", status: "ok", uploaded: 6, skipped: 0, discovered: 2 }],
  ...over,
});

// ── recipient parsing ──────────────────────────────────────────────────────

test("recipients accept comma, semicolon and whitespace separation", () => {
  assert.deepEqual(parseRecipients("a@x.com,b@y.com"), ["a@x.com", "b@y.com"]);
  assert.deepEqual(parseRecipients("a@x.com; b@y.com"), ["a@x.com", "b@y.com"]);
  assert.deepEqual(parseRecipients("a@x.com\n b@y.com"), ["a@x.com", "b@y.com"]);
});

test("malformed entries are separated out rather than silently dropped", () => {
  assert.deepEqual(parseRecipients("good@x.com, notanemail, b@y.com"), ["good@x.com", "b@y.com"]);
  assert.deepEqual(invalidRecipients("good@x.com, notanemail"), ["notanemail"]);
});

test("an empty or unset list yields no recipients", () => {
  assert.deepEqual(parseRecipients(""), []);
  assert.deepEqual(parseRecipients(undefined), []);
});

// ── status derivation ──────────────────────────────────────────────────────

test("overallStatus distinguishes the outcomes an operator reacts to differently", () => {
  assert.equal(overallStatus(baseSummary()), "OK");
  assert.equal(overallStatus(baseSummary({ fatalError: { name: "E", message: "m" } })), "FATAL");
  assert.equal(overallStatus(baseSummary({
    schools: [{ school: "A", status: "failed", uploaded: 0 }],
  })), "FAILED");
  assert.equal(overallStatus(baseSummary({
    schools: [{ school: "A", status: "ok", uploaded: 3, uploadErrors: 1 }],
  })), "PARTIAL");
  // An export that never materialised must NOT read as success.
  assert.equal(overallStatus(baseSummary({
    schools: [{ school: "A", status: "ok", uploaded: 3, exportFailures: [{ id: "1", title: "t", reason: "r" }] }],
  })), "PARTIAL");
  assert.equal(overallStatus(baseSummary({
    schools: [{ school: "A", status: "ok", uploaded: 0 }],
  })), "NO-DATA");
});

test("the subject line leads with the verdict and the scope", () => {
  assert.match(buildSubject(baseSummary()), /^\[GAINS scrape\] OK — Athenian — 6 file\(s\)$/);
  assert.match(buildSubject(baseSummary({ dryRun: true })), /\(dry-run\)$/);
  assert.match(buildSubject(baseSummary({ schoolFilter: null })), /all schools/);
});

// ── body content ───────────────────────────────────────────────────────────

test("the body names every actionable failure", () => {
  const body = buildBody(baseSummary({
    schools: [{
      school: "Athenian", shortName: "Athenian", status: "ok", uploaded: 3, skipped: 1, discovered: 2,
      uploadErrors: 1,
      exportFailures: [{ id: "999", title: "Quiz 1", reason: "no new transfer rows" }],
      incompleteExports: [{ id: "888", title: "Quiz 2", missing: ["Question-Data"] }],
      keyWarnings: ['category: "A/B" -> "A_B"'],
    }],
  }));
  assert.match(body, /Status:\s+PARTIAL/);
  assert.match(body, /999.*Quiz 1.*no new transfer rows/);
  assert.match(body, /888.*Quiz 2.*missing Question-Data/);
  assert.match(body, /upload errors: 1/);
  assert.match(body, /key sanitised/);
});

test("a fatal abort is stated at the top, not buried", () => {
  const body = buildBody(baseSummary({
    fatalError: { name: "FetchError", message: "backend unreachable" },
    schools: [],
  }));
  assert.match(body, /Status:\s+FATAL/);
  assert.match(body, /FetchError: backend unreachable/);
});

test("the body says what happens next, so nobody assumes reports refreshed", () => {
  const body = buildBody(baseSummary());
  assert.match(body, /lands these into raw_\* and stops/);
  assert.match(body, /does NOT rebuild reports/);
});

// ── send behaviour ─────────────────────────────────────────────────────────

test("no recipients configured => no send, and it is not treated as an error", async () => {
  const log = collectLog();
  const res = await sendRunSummary(baseSummary(), { env: {}, log });
  assert.equal(res.sent, false);
  assert.equal(res.reason, "no recipients");
  assert.equal(log.lines.error.length, 0);
  assert.equal(log.lines.info.length, 1, "should say once why no mail arrived");
});

test("recipients WITHOUT a transport is an ERROR — silent alert loss is the worst case", async () => {
  const log = collectLog();
  const res = await sendRunSummary(baseSummary(), {
    env: { SCRAPER_NOTIFY_EMAILS: "a@x.com" }, log,
  });
  assert.equal(res.sent, false);
  assert.equal(res.reason, "transport not configured");
  assert.equal(log.lines.error.length, 1);
  assert.match(log.lines.error[0], /RESEND_API_KEY/);
});

test("a successful send posts to the provider with all recipients", async () => {
  const calls = [];
  const fetchImpl = async (url, opts) => {
    calls.push({ url, body: JSON.parse(opts.body), auth: opts.headers.Authorization });
    return { ok: true, status: 200, text: async () => "" };
  };
  const res = await sendRunSummary(baseSummary(), {
    env: {
      SCRAPER_NOTIFY_EMAILS: "a@x.com,b@y.com",
      RESEND_API_KEY: "re_test",
      SCRAPER_NOTIFY_FROM: "gains@example.com",
    },
    log: collectLog(),
    fetchImpl,
  });
  assert.equal(res.sent, true);
  assert.equal(res.recipients, 2);
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].body.to, ["a@x.com", "b@y.com"]);
  assert.equal(calls[0].body.from, "gains@example.com");
  assert.match(calls[0].auth, /^Bearer re_test$/);
});

test("a provider rejection is reported but never thrown", async () => {
  const log = collectLog();
  const fetchImpl = async () => ({ ok: false, status: 422, text: async () => "bad from address" });
  const res = await sendRunSummary(baseSummary(), {
    env: { SCRAPER_NOTIFY_EMAILS: "a@x.com", RESEND_API_KEY: "k", SCRAPER_NOTIFY_FROM: "f@x.com" },
    log, fetchImpl,
  });
  assert.equal(res.sent, false);
  assert.equal(res.reason, "provider 422");
  assert.match(log.lines.error[0], /rejected by provider/);
});

test("a thrown transport error is swallowed — a mail outage cannot fail a good run", async () => {
  const log = collectLog();
  const fetchImpl = async () => { throw new Error("ECONNRESET"); };
  const res = await sendRunSummary(baseSummary(), {
    env: { SCRAPER_NOTIFY_EMAILS: "a@x.com", RESEND_API_KEY: "k", SCRAPER_NOTIFY_FROM: "f@x.com" },
    log, fetchImpl,
  });
  assert.equal(res.sent, false);
  assert.equal(log.lines.error.length, 1);
});

test("SCRAPER_NOTIFY_ON=failure suppresses OK but never suppresses a real failure", async () => {
  const env = {
    SCRAPER_NOTIFY_EMAILS: "a@x.com", RESEND_API_KEY: "k",
    SCRAPER_NOTIFY_FROM: "f@x.com", SCRAPER_NOTIFY_ON: "failure",
  };
  let sends = 0;
  const fetchImpl = async () => { sends += 1; return { ok: true, status: 200, text: async () => "" }; };

  const ok = await sendRunSummary(baseSummary(), { env, log: collectLog(), fetchImpl });
  assert.equal(ok.sent, false);
  assert.equal(sends, 0);

  const bad = await sendRunSummary(
    baseSummary({ schools: [{ school: "A", status: "failed", uploaded: 0 }] }),
    { env, log: collectLog(), fetchImpl },
  );
  assert.equal(bad.sent, true);
  assert.equal(sends, 1);

  const fatal = await sendRunSummary(
    baseSummary({ fatalError: { name: "E", message: "m" } }),
    { env, log: collectLog(), fetchImpl },
  );
  assert.equal(fatal.sent, true, "a FATAL run must always notify");
});


// ── sendRunSummary must NEVER throw (adversarial-review fix) ────────────────
// main() awaits this from a `finally`, so a throw here would REPLACE the run's
// real outcome: a fully successful scrape would reject, exit 1, and lose the
// email. Rendering used to happen outside the try, which made that reachable
// from any malformed ledger entry.

test("a school row missing `status` does not throw — it degrades", async () => {
  const log = collectLog();
  let sent = null;
  const fetchImpl = async (url, opts) => {
    sent = JSON.parse(opts.body);
    return { ok: true, status: 200, text: async () => "" };
  };
  const res = await sendRunSummary(
    { runId: "r", startedAt: "t", durationSec: "1", schools: [{ school: "X", uploaded: 1 }], storageKeys: [] },
    {
      env: { SCRAPER_NOTIFY_EMAILS: "a@x.com", RESEND_API_KEY: "k", SCRAPER_NOTIFY_FROM: "f@x.com" },
      log, fetchImpl,
    },
  );
  assert.equal(res.sent, true, "must still deliver something");
  assert.ok(sent.subject.length > 0);
  assert.ok(log.lines.error.length >= 1, "the rendering failure must be logged");
});

test("a summary with no schools array does not throw", async () => {
  const res = await sendRunSummary(
    { runId: "r", startedAt: "t", durationSec: "1", storageKeys: [] },
    {
      env: { SCRAPER_NOTIFY_EMAILS: "a@x.com", RESEND_API_KEY: "k", SCRAPER_NOTIFY_FROM: "f@x.com" },
      log: collectLog(),
      fetchImpl: async () => ({ ok: true, status: 200, text: async () => "" }),
    },
  );
  assert.equal(res.sent, true);
});

test("a completely empty summary object still does not throw", async () => {
  const res = await sendRunSummary({}, {
    env: { SCRAPER_NOTIFY_EMAILS: "a@x.com", RESEND_API_KEY: "k", SCRAPER_NOTIFY_FROM: "f@x.com" },
    log: collectLog(),
    fetchImpl: async () => ({ ok: true, status: 200, text: async () => "" }),
  });
  assert.equal(res.sent, true);
});
