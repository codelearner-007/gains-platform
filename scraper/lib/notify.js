/**
 * Per-run email notification.
 *
 * WHY IT LIVES IN THE SCRAPER, NOT THE BACKEND
 * The backend has no mail code, no mail dependency and no mail settings, so
 * "POST the summary to the backend" would mean writing a brand-new provider
 * integration in Python plus an authenticated endpoint plus a deploy — and it
 * would still call the same provider HTTP API in the end. Worse, it breaks the
 * one requirement that matters: a FAILED run must be able to report itself. The
 * scraper's most likely failures are exactly the ones where the backend is
 * implicated (scraper-config unreachable, scraper-complete rejected), so routing
 * the alert through the backend would silence the alarm precisely when it is
 * needed.
 *
 * Resend's REST API is called with Node's global `fetch` — no SDK, so the
 * dependency list stays at playwright + dotenv + @supabase/supabase-js.
 *
 * FAILURE POLICY: sending mail must never change the outcome of a run. A send
 * failure is logged as an ERROR and swallowed; it does not mask a successful
 * scrape, and it does not rescue a failed one.
 */

const { redact } = require("./logger");

const RESEND_ENDPOINT = "https://api.resend.com/emails";

/** Extract the address from a `Name <addr@host>` form, else return as-is. */
function unwrapAddress(token) {
  const m = String(token).match(/<([^>]+)>/);
  return m ? m[1].trim() : String(token).trim();
}

/**
 * Split a recipient list. Commas and semicolons separate; whitespace does too,
 * EXCEPT inside a `Name <addr>` form, which is split off first so a display name
 * is not shredded into bogus tokens.
 */
function splitRecipients(raw) {
  const angled = [];
  const rest = String(raw).replace(/[^,;]*<[^>]+>/g, (m) => {
    angled.push(unwrapAddress(m));
    return "";
  });
  return [...angled, ...rest.split(/[,;\s]+/)].map((s) => s.trim()).filter(Boolean);
}

/**
 * Deliberately loose: enough to catch a stray word or a missing @, without
 * pretending to implement RFC 5322. Bounded so one very long token cannot make the
 * match pathological.
 */
const isAddress = (s) => s.length <= 320 && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(s);

/**
 * Split one env string into usable and unusable recipients in a single pass.
 * These were two functions with the same predicate NEGATED, which had to stay in
 * sync or a token would end up neither used nor warned about.
 */
function classifyRecipients(raw) {
  const valid = [];
  const invalid = [];
  for (const token of raw ? splitRecipients(raw) : []) {
    (isAddress(token) ? valid : invalid).push(token);
  }
  return { valid, invalid };
}

function parseRecipients(raw) { return classifyRecipients(raw).valid; }

/** Recipients present in the env but not shaped like addresses — worth warning about. */
function invalidRecipients(raw) { return classifyRecipients(raw).invalid; }

function readConfig(env = process.env) {
  const { valid, invalid } = classifyRecipients(env.SCRAPER_NOTIFY_EMAILS || "");
  return {
    recipients: valid,
    invalid,
    apiKey: env.RESEND_API_KEY || "",
    from: env.SCRAPER_NOTIFY_FROM || "",
    // "always" (default) or "failure" — some operators only want to hear about problems.
    when: String(env.SCRAPER_NOTIFY_ON || "always").toLowerCase(),
  };
}

/** One-line verdict for the subject line. */
function overallStatus(summary) {
  if (summary.fatalError) return "FATAL";
  const failed = summary.schools.filter((s) => s.status !== "ok").length;
  const partial = summary.schools.filter(
    (s) => s.status === "ok" && ((s.uploadErrors || 0) > 0
      || (s.incompleteExports || []).length > 0
      || (s.exportFailures || []).length > 0),
  ).length;
  if (failed > 0) return "FAILED";
  if (partial > 0) return "PARTIAL";
  if (summary.schools.every((s) => (s.uploaded || 0) === 0)) return "NO-DATA";
  return "OK";
}

function buildSubject(summary) {
  const status = overallStatus(summary);
  const scope = summary.schoolFilter ? summary.schoolFilter : "all schools";
  const uploaded = summary.schools.reduce((n, s) => n + (s.uploaded || 0), 0);
  return `[GAINS scrape] ${status} — ${scope} — ${uploaded} file(s)`
    + `${summary.dryRun ? " (dry-run)" : ""}`;
}

/**
 * Plain-text body. Deliberately text-first: it is what lands in a phone
 * notification preview, it survives every client, and it is greppable.
 * The body leads with the verdict and the reasons — an operator should not have
 * to scroll to learn whether they need to act.
 */
function buildBody(summary) {
  const L = [];
  const status = overallStatus(summary);

  L.push(`Status:    ${status}`);
  L.push(`Run id:    ${summary.runId}`);
  L.push(`Scope:     ${summary.schoolFilter || "all active schools"}${summary.assessmentFilter ? ` | assessment~"${summary.assessmentFilter}"` : ""}`);
  L.push(`Started:   ${summary.startedAt}`);
  L.push(`Duration:  ${summary.durationSec}s`);
  L.push(`Mode:      ${summary.dryRun ? "dry-run (no export/upload)" : "live"}`);
  L.push(`Env:       backend=${summary.backendBaseUrl} storage=${summary.supabaseHost} bucket=${summary.bucket}`);
  L.push("");

  if (summary.fatalError) {
    L.push("FATAL — the run aborted before completing:");
    L.push(`  ${summary.fatalError.name}: ${summary.fatalError.message}`);
    L.push("");
  }

  for (const s of summary.schools) {
    const errs = s.uploadErrors || 0;
    const inc = s.incompleteExports || [];
    const expf = s.exportFailures || [];
    L.push(`── ${s.school} [${s.status.toUpperCase()}]`);
    L.push(`     assessments discovered: ${s.discovered ?? "?"}`);
    L.push(`     exported: ${s.exported ?? s.discovered ?? "?"} | skipped: ${s.skipped ?? 0} | files uploaded: ${s.uploaded ?? 0}`);
    if (s.status !== "ok") {
      L.push(`     ERROR [${s.errorClass}] ${s.error}`);
    }
    if (errs) L.push(`     upload errors: ${errs}`);
    for (const e of expf) L.push(`     export FAILED: ${e.id} "${e.title}" — ${e.reason}`);
    for (const e of inc) L.push(`     incomplete triplet: ${e.id} "${e.title}" missing ${e.missing.join(", ")}`);
    for (const w of s.keyWarnings || []) L.push(`     key sanitised: ${w}`);
    // The funnel is the whole point of the zero-discovery case: without it the
    // email says "0 assessments" and the operator still has to open the log.
    if ((s.discovered === 0 || s.status !== "ok") && s.funnel) {
      const f = s.funnel;
      L.push(`     why nothing was discovered: courses=${f.courses} sections=${f.sections} `
        + `assignmentsSeen=${f.assignments}`);
      const reasons = [
        ["unmapped subject/grade (course skipped)", f.coursesSkippedSubjectGrade],
        ["section had no matching grading category", f.sectionsSkippedNoMatchingCategory],
        ["section had zero grading categories", f.sectionsWithZeroCategories],
        ["not type=assessment", f.notAssessmentType],
        ["grading category did not match the regex", f.categoryUnmatched],
        ["excluded by --assessment", f.filteredByAssessmentFlag],
        ["outside the due window", f.outsideDueWindow],
        ["no due date (use --include-undated)", f.undatedExcluded],
        ["due in the future (use --due-until)", f.futureDated],
        ["unreadable web_url", f.badWebUrl],
      ].filter(([, n]) => n > 0);
      for (const [why, n] of reasons) L.push(`       ${n} × ${why}`);
    }
    L.push("");
  }

  if (summary.storageKeys && summary.storageKeys.length) {
    L.push(`Uploaded objects (${summary.storageKeys.length}):`);
    for (const k of summary.storageKeys.slice(0, 40)) L.push(`  ${k}`);
    if (summary.storageKeys.length > 40) {
      L.push(`  … and ${summary.storageKeys.length - 40} more`);
    }
    L.push("");
  }

  L.push("Next step: the backend worker lands these into raw_* and stops.");
  L.push("It does NOT rebuild reports — see docs/audit/fixes/03_prod_data_sync_runbook.md.");
  L.push("");
  L.push("Check the ledger:");
  L.push("  SELECT run_id, status, files_processed, rows_inserted, error_count");
  L.push("  FROM ingestion_runs ORDER BY started_at DESC LIMIT 3;");

  return L.join("\n");
}

/**
 * Send the run-summary email. Never throws.
 * @returns {Promise<{sent: boolean, reason?: string, recipients?: number}>}
 */
async function sendRunSummary(summary, { env = process.env, log = null, fetchImpl = null } = {}) {
  const cfg = readConfig(env);
  const doFetch = fetchImpl || globalThis.fetch;

  if (cfg.invalid.length) {
    log?.warn("ignoring malformed entries in SCRAPER_NOTIFY_EMAILS", {
      ignored: cfg.invalid.join(","),
    });
  }

  if (!cfg.recipients.length) {
    // Not an error: notification is opt-in. Say so once so an operator who
    // EXPECTED mail can see why none arrived.
    log?.info("no run-summary email sent: SCRAPER_NOTIFY_EMAILS is unset or has no valid addresses");
    return { sent: false, reason: "no recipients" };
  }

  // Rendering is inside a try because it walks caller-supplied summary data.
  // It used to run before the try, so a malformed ledger entry threw OUT of a
  // function documented as never throwing — and since main() awaits this from a
  // `finally`, that rejection replaced the run's real outcome AND lost the email.
  let status;
  try {
    status = overallStatus(summary);
  } catch (err) {
    log?.error("could not derive run status for the notification email", err);
    status = "UNKNOWN";
  }
  if (cfg.when === "failure" && (status === "OK" || status === "NO-DATA")) {
    log?.info("run-summary email suppressed by SCRAPER_NOTIFY_ON=failure", { status });
    return { sent: false, reason: "suppressed by policy" };
  }

  if (!cfg.apiKey || !cfg.from) {
    // Recipients were configured but the transport was not — that IS a
    // misconfiguration and must be loud, or alerts silently never arrive.
    log?.error(
      "run-summary email NOT sent: recipients are configured but "
      + `${!cfg.apiKey ? "RESEND_API_KEY" : "SCRAPER_NOTIFY_FROM"} is missing`,
      null,
      { recipients: cfg.recipients.length },
    );
    return { sent: false, reason: "transport not configured" };
  }

  if (typeof doFetch !== "function") {
    log?.error("run-summary email NOT sent: global fetch unavailable (needs Node >= 18)");
    return { sent: false, reason: "no fetch" };
  }

  let payload;
  try {
    payload = {
      from: cfg.from,
      to: cfg.recipients,
      // Redacted like a log line: the body embeds third-party error strings, and
      // email is a wider egress channel than stdout — it must not be the weaker
      // hygiene path for the same text.
      subject: redact(buildSubject(summary)),
      text: redact(buildBody(summary)),
    };
  } catch (err) {
    // A summary we cannot render must still produce an alert — a bare "the run
    // finished and the report broke" beats silence.
    log?.error("could not render the run-summary email; sending a minimal fallback", err);
    payload = {
      from: cfg.from,
      to: cfg.recipients,
      subject: `[GAINS scrape] ${status} — summary could not be rendered`,
      text: `Run ${summary?.runId || "(unknown)"} finished with status ${status}, but the `
        + `summary could not be rendered: ${err && err.message}\n\n`
        + "Check the run log directly.",
    };
  }

  try {
    const res = await doFetch(RESEND_ENDPOINT, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${cfg.apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      // A hung mail provider must not hold a finished scrape open.
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      log?.error("run-summary email rejected by provider", null, {
        status: res.status, body: body.substring(0, 200),
      });
      return { sent: false, reason: `provider ${res.status}` };
    }
    log?.info("run-summary email sent", { recipients: cfg.recipients.length, status });
    return { sent: true, recipients: cfg.recipients.length };
  } catch (err) {
    // Swallowed by design: a mail outage must not change the run's verdict.
    log?.error("run-summary email failed to send", err, { recipients: cfg.recipients.length });
    return { sent: false, reason: err.name || "send failed" };
  }
}

module.exports = {
  parseRecipients,
  invalidRecipients,
  readConfig,
  overallStatus,
  buildSubject,
  buildBody,
  sendRunSummary,
  RESEND_ENDPOINT,
};
