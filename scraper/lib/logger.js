/**
 * Structured, leveled logger for unattended runs.
 *
 * The previous logger was `console.log("[HH:MM:SS] " + msg)`. For an operator
 * debugging a failed 03:00 cron run from Railway logs alone, that loses four
 * things that turned out to matter every time:
 *
 *   1. **A date.** An overnight run could not be ordered, or joined against a
 *      Railway deploy window.
 *   2. **Severity.** Everything went to stdout, so `grep`-ing for errors was
 *      impossible and a collector could not alert on level.
 *   3. **Identity.** Per-assessment lines carried no school and often no
 *      assessment id, so in a multi-school run you could not tell whose failure
 *      you were reading.
 *   4. **A run id.** Nothing tied a log line to the `ingestion_runs` row the
 *      backend later created.
 *
 * Design rules, deliberately narrow:
 *   - ISO-8601 UTC timestamps (sortable, unambiguous, joinable).
 *   - WARN/ERROR go to **stderr** so a collector can split streams.
 *   - Context (`runId`, `school`, `assessment`) is bound once and prefixed
 *     automatically — call sites stay short and cannot forget it.
 *   - `debug` is OFF unless SCRAPER_LOG_LEVEL=debug, so the per-attempt polling
 *     chatter that used to dominate a healthy run is available when
 *     investigating and silent otherwise.
 */

const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };

function envLevel() {
  const raw = String(process.env.SCRAPER_LOG_LEVEL || "info").toLowerCase();
  return LEVELS[raw] ?? LEVELS.info;
}

/** Redact anything that looks like a credential before it reaches a log line. */
function redact(value) {
  if (value === undefined || value === null) return value;
  let s = String(value);
  // Bearer/JWT-ish and long opaque tokens.
  s = s.replace(/eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g, "<jwt>");
  s = s.replace(/(oauth_signature=")[^"]+(")/g, '$1<redacted>$2');
  s = s.replace(/(oauth_consumer_key=")[^"]+(")/g, '$1<redacted>$2');
  s = s.replace(/(password"?\s*[:=]\s*"?)[^",\s}]+/gi, "$1<redacted>");
  s = s.replace(/(secret"?\s*[:=]\s*"?)[^",\s}]+/gi, "$1<redacted>");
  s = s.replace(/(apikey"?\s*[:=]\s*"?)[^",\s}]+/gi, "$1<redacted>");
  return s;
}

class Logger {
  constructor(context = {}, min = envLevel()) {
    this.context = context;
    this.min = min;
  }

  /** Derive a child logger carrying extra context (school, assessment, …). */
  child(extra) {
    return new Logger({ ...this.context, ...extra }, this.min);
  }

  _prefix() {
    const { runId, school, assessment } = this.context;
    const parts = [];
    if (runId) parts.push(runId);
    if (school) parts.push(school);
    if (assessment) parts.push(`a=${assessment}`);
    return parts.length ? ` [${parts.join(" | ")}]` : "";
  }

  _emit(level, msg, fields) {
    if (LEVELS[level] < this.min) return;
    const ts = new Date().toISOString();
    let line = `${ts} ${level.toUpperCase().padEnd(5)}${this._prefix()} ${redact(msg)}`;
    if (fields && Object.keys(fields).length) {
      const flat = Object.entries(fields)
        .filter(([, v]) => v !== undefined && v !== null && v !== "")
        .map(([k, v]) => `${k}=${redact(v)}`)
        .join(" ");
      if (flat) line += ` | ${flat}`;
    }
    // WARN/ERROR to stderr so streams can be split and alerted on separately.
    (LEVELS[level] >= LEVELS.warn ? console.error : console.log)(line);
  }

  debug(msg, fields) { this._emit("debug", msg, fields); }
  info(msg, fields) { this._emit("info", msg, fields); }
  warn(msg, fields) { this._emit("warn", msg, fields); }

  /**
   * Errors always carry the error CLASS and, at debug level, the stack. The old
   * code reduced every failure to `err.message.substring(0, 120)`, which threw
   * away exactly the information needed to tell a TypeError from a timeout.
   */
  error(msg, err, fields) {
    const extra = { ...(fields || {}) };
    if (err) {
      extra.errClass = err.name || err.constructor?.name || typeof err;
      extra.errMsg = err.message || String(err);
      if (err.status !== undefined) extra.status = err.status;
    }
    this._emit("error", msg, extra);
    // Full stack once, at debug level, so the default log stays readable but the
    // stack is never permanently lost.
    if (err && err.stack && this.min <= LEVELS.debug) {
      console.error(redact(err.stack));
    }
  }
}

module.exports = { Logger, LEVELS, redact };
