/**
 * Storage-key construction and the due-date window.
 *
 * The storage key is a FROZEN CONTRACT with the backend:
 *
 *   <short_name>/<session>/<category>/<subject>/<grade>/<section>/<originalFilename>.csv
 *
 * `backend/app/jobs/file_path_parser.py` parses it POSITIONALLY and END-ANCHORED
 * (session = parts[0]; section/grade/subject = parts[-2]/[-3]/[-4]). It does not
 * validate. So a segment containing "/" does not fail — it invents a path level,
 * shifts every later segment by one, and lands the rows under a WRONG
 * subject/grade/section.
 *
 * Previously only the SECTION segment was sanitised. `session` and
 * `categoryFolder` were interpolated raw, and `categoryFolder` comes from a live
 * Schoology grading-category title — free text an administrator can rename to
 * anything, including "Quizzes/Tests".
 */

// Windows-illegal characters plus C0 control characters, written with explicit
// \u escapes so the class is readable. An earlier form embedded literal control
// bytes, which rendered in a terminal as "* -" and looked as though space and
// hyphen were included.
//
// SPACE AND HYPHEN ARE DELIBERATELY EXCLUDED. The category literal is
// "1 - Lesson  Assessments": the backend derives assessment_type by stripping
// everything up to the first "-", and the DOUBLE space after "Lesson" survives
// into every downstream dimension key. Replacing " " or "-" here would reshape
// that segment and fork the assessment-type dimension on the next run.
const UNSAFE_SEGMENT_CHARS = /[<>:"/\\|?*\u0000-\u001f]/g;

/**
 * Make an arbitrary string safe as ONE path segment.
 *
 * Internal whitespace is preserved on purpose (see the note above the regex).
 */
function safeSegment(value) {
  const s = String(value === undefined || value === null ? "" : value);
  // Trim FIRST: the leading-dot guard used to run before trim, so " .. " kept its
  // leading space, dodged the guard, and survived as ".." — a relative path
  // component inside a storage key.
  return s.replace(UNSAFE_SEGMENT_CHARS, "_").trim().replace(/^\.+/, "_");
}

/**
 * Build the storage key relative to the school root, sanitising every segment.
 *
 * Returns { key, warnings }. `warnings` names any segment that had to be changed,
 * so an upstream rename shows up in the log instead of silently reshaping data.
 * An empty segment is fatal: it would collapse the 5-segment shape the backend
 * parser depends on, and padding it would invent data.
 */
function buildRelativeSegments({ session, category, subject, grade, section }) {
  const warnings = [];
  const seg = (name, raw) => {
    const safe = safeSegment(raw);
    if (safe !== String(raw === undefined || raw === null ? "" : raw).trim()) {
      warnings.push(`${name}: ${JSON.stringify(raw)} -> ${JSON.stringify(safe)}`);
    }
    return safe;
  };

  const parts = [
    seg("session", session),
    seg("category", category),
    seg("subject", subject),
    seg("grade", grade),
    seg("section", section),
  ];

  if (parts.some((p) => p === "")) {
    const err = new Error(
      "refusing to build a storage key with an empty segment: "
      + `session=${JSON.stringify(session)} category=${JSON.stringify(category)} `
      + `subject=${JSON.stringify(subject)} grade=${JSON.stringify(grade)} `
      + `section=${JSON.stringify(section)}`,
    );
    err.name = "StorageKeyError";
    throw err;
  }

  return { segments: parts, warnings };
}

/**
 * The 5-segment prefix, trailing slash included — what discovery stores per
 * assessment before any filename is known.
 */
function buildRelativePrefix(fields) {
  const { segments, warnings } = buildRelativeSegments(fields);
  return { prefix: `${segments.join("/")}/`, warnings };
}

/**
 * Full key for one downloaded file. `filename` must be non-empty.
 *
 * The filename is sanitised like every other component. It is NOT a safe slug:
 * Schoology builds it from the admin-authored assessment title, so a title such
 * as "Unit 3/4 Review" yields "Question-Data-Unit 3/4 Review.csv". A "/" there
 * adds a path level, and the backend parser deliberately tolerates 7+ parts (it
 * absorbs an interposed category folder), so the row set is silently MISFILED
 * rather than rejected — subject/grade/section each shift by one.
 */
function buildRelativeKey(fields) {
  const { filename } = fields;
  if (!filename) {
    const err = new Error("refusing to build a storage key with an empty filename");
    err.name = "StorageKeyError";
    throw err;
  }
  const { segments, warnings } = buildRelativeSegments(fields);
  const safeName = safeSegment(filename);
  if (!safeName) {
    const err = new Error(
      `filename sanitised to nothing: ${JSON.stringify(filename)}`,
    );
    err.name = "StorageKeyError";
    throw err;
  }
  if (safeName !== String(filename).trim()) {
    warnings.push(`filename: ${JSON.stringify(filename)} -> ${JSON.stringify(safeName)}`);
  }
  return { key: `${segments.join("/")}/${safeName}`, warnings };
}

// ── Due-date window ────────────────────────────────────────────────────────
// The legacy bot shifted every due date by a hardcoded +5h ("midnight EST → UTC")
// and compared UTC calendar dates. That is wrong for the ~8 months Florida is on
// EDT (UTC-4), and it made "today" mean today on the RUNNER's clock.
//
// Both problems disappear by doing no timezone arithmetic on the due date at all:
// Schoology emits `due` as a naive school-local timestamp ("YYYY-MM-DD HH:MM:SS"),
// so its first 10 characters ARE the school-local calendar date. Only the window
// BOUNDS need a timezone, taken from schools.timezone.

// Constructing Intl.DateTimeFormat dominates this function's cost (~93 µs built
// per call vs ~1.3 µs reused) and a run only ever sees a handful of zones, so cache
// the formatter per zone. `null` caches the unknown-zone case too.
const _dateFormatters = new Map();

function _formatterFor(timeZone) {
  if (_dateFormatters.has(timeZone)) return _dateFormatters.get(timeZone);
  let fmt = null;
  try {
    // en-CA formats as YYYY-MM-DD, and Intl applies the zone's DST rules.
    fmt = new Intl.DateTimeFormat("en-CA", {
      timeZone, year: "numeric", month: "2-digit", day: "2-digit",
    });
  } catch {
    fmt = null;
  }
  _dateFormatters.set(timeZone, fmt);
  return fmt;
}

/** Calendar date (YYYY-MM-DD) of `instant` as observed in `timeZone`. */
function calendarDateIn(timeZone, instant) {
  const fmt = _formatterFor(timeZone);
  // Unknown/absent zone → UTC rather than throwing mid-discovery.
  return fmt ? fmt.format(instant) : instant.toISOString().substring(0, 10);
}

/** School-local calendar date of a Schoology `due` value, or null if unparseable. */
function dueCalendarDate(dueDateStr, timeZone) {
  if (!dueDateStr) return null;
  const direct = String(dueDateStr).trim().match(/^(\d{4}-\d{2}-\d{2})/);
  if (direct) return direct[1];
  const parsed = new Date(dueDateStr);
  if (Number.isNaN(parsed.getTime())) return null;
  // Reuse calendarDateIn. The hand-rolled formatting this replaces used the
  // RUNNER's clock — reintroducing the very dependence this module removes — for
  // any value that is Date-parseable but not YYYY-MM-DD-prefixed ("07/15/2026").
  return calendarDateIn(timeZone, parsed);
}

/**
 * Academic session ("2025-26") for an instant, in the SCHOOL's timezone.
 *
 * Previously derived from the runner's local month/year via
 * `currentDate.getMonth()`. A container on UTC between 00:00 and 04:00 ET, or a
 * run near the 1 August rollover, therefore computed a DIFFERENT year than the
 * school was in — and the session is the FIRST path segment, so every row would
 * land under the wrong academic year.
 */
function academicSession(timeZone, instant) {
  const [y, m] = calendarDateIn(timeZone, instant).split("-").map(Number);
  // August or later => the year now starting; before August => the one that
  // started last calendar year.
  const startYear = m >= 8 ? y : y - 1;
  return `${startYear}-${String((startYear + 1) % 100).padStart(2, "0")}`;
}

/**
 * Inclusive [from, to] window of school-local calendar dates.
 *
 * The lower bound is walked back a CALENDAR day at a time rather than by
 * `windowDays * 86400000`. A day is not 86,400,000 ms across a DST transition, so
 * fixed-millisecond arithmetic lands on the wrong calendar date twice a year —
 * exactly the class of off-by-one-day bug this module exists to remove.
 */
function computeDueWindow({ timezone, windowDays, dueUntil, now }) {
  const today = calendarDateIn(timezone, now);
  let cursor = now;
  // Carry the previous iteration's answer forward rather than recomputing it.
  let cursorDay = today;
  for (let i = 0; i < windowDays; i += 1) {
    // Step back 24h then re-read the local date; if DST made that land on the same
    // calendar day, step again so each iteration moves exactly one day.
    let next = new Date(cursor.getTime() - 86400000);
    let nextDay = calendarDateIn(timezone, next);
    if (nextDay === cursorDay) {
      next = new Date(next.getTime() - 3600000);
      nextDay = calendarDateIn(timezone, next);
    }
    cursor = next;
    cursorDay = nextDay;
  }
  const from = cursorDay;
  return { from, to: dueUntil && dueUntil > today ? dueUntil : today, today };
}

/** Does this assessment's due date fall in the window? */
function isDueInWindow(dueDateStr, window, { includeUndated, timezone } = {}) {
  // "Absent" and "unparseable" are deliberately NOT the same case.
  // --include-undated means "Schoology left the due date empty", which is common
  // on hand-made assessments. A present-but-garbled value is a data problem;
  // including it would widen the window on the rows we understand least.
  const isAbsent = dueDateStr === null || dueDateStr === undefined
    || String(dueDateStr).trim() === "";
  if (isAbsent) return Boolean(includeUndated);

  const day = dueCalendarDate(dueDateStr, timezone);
  if (day === null) return false;
  return day >= window.from && day <= window.to;
}

module.exports = {
  safeSegment,
  buildRelativeSegments,
  buildRelativePrefix,
  buildRelativeKey,
  calendarDateIn,
  dueCalendarDate,
  academicSession,
  computeDueWindow,
  isDueInWindow,
  UNSAFE_SEGMENT_CHARS,
};
