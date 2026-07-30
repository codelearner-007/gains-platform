/**
 * Due-window unit tests (node --test).
 *
 * These pin the behaviour that decides whether an assessment is discovered at
 * all. The legacy implementation shifted every due date by a hardcoded +5h
 * ("midnight EST → UTC") and then compared UTC calendar dates, which is wrong
 * for the ~8 months a year Florida observes EDT (UTC-4) and also made "today"
 * mean today on the runner's clock rather than at the school.
 */
const test = require("node:test");
const assert = require("node:assert/strict");

const {
  calendarDateIn,
  dueCalendarDate,
  computeDueWindow,
  isDueInWindow,
  safeSegment,
  buildRelativePrefix,
  buildRelativeKey,
  academicSession,
} = require("../lib/paths.js");

const TZ = "America/New_York";

// ── calendarDateIn: the school-local "today" ───────────────────────────────

test("calendarDateIn resolves the school-local date across the UTC midnight gap", () => {
  // 03:30 UTC on Jul 16 is still Jul 15 at 23:30 in New York (EDT, UTC-4).
  // A UTC-based "today" would call this Jul 16 and drop a Jul-15 assessment.
  assert.equal(calendarDateIn(TZ, new Date("2026-07-16T03:30:00Z")), "2026-07-15");
  assert.equal(calendarDateIn(TZ, new Date("2026-07-16T04:30:00Z")), "2026-07-16");
});

test("calendarDateIn honours EST vs EDT rather than a fixed offset", () => {
  // January = EST (UTC-5): 04:30Z is still the previous day locally.
  assert.equal(calendarDateIn(TZ, new Date("2026-01-16T04:30:00Z")), "2026-01-15");
  // July = EDT (UTC-4): the same wall clock is already the new day.
  assert.equal(calendarDateIn(TZ, new Date("2026-07-16T04:30:00Z")), "2026-07-16");
});

test("calendarDateIn falls back to UTC for an unknown timezone instead of throwing", () => {
  assert.equal(calendarDateIn("Not/AZone", new Date("2026-07-16T03:30:00Z")), "2026-07-16");
  assert.equal(calendarDateIn(undefined, new Date("2026-07-16T03:30:00Z")), "2026-07-16");
});

// ── dueCalendarDate: Schoology's naive school-local timestamp ──────────────

test("dueCalendarDate takes the date portion verbatim — no timezone arithmetic", () => {
  // The regression the +5h hack caused: a late-evening due time must NOT roll
  // over to the next day.
  assert.equal(dueCalendarDate("2026-07-15 23:55:00"), "2026-07-15");
  assert.equal(dueCalendarDate("2026-07-15 00:00:00"), "2026-07-15");
  assert.equal(dueCalendarDate("2026-07-15"), "2026-07-15");
  assert.equal(dueCalendarDate("2026-07-15T23:55:00"), "2026-07-15");
});

test("dueCalendarDate reports null for absent or unparseable values", () => {
  assert.equal(dueCalendarDate(""), null);
  assert.equal(dueCalendarDate(null), null);
  assert.equal(dueCalendarDate(undefined), null);
  assert.equal(dueCalendarDate("not a date"), null);
});

// ── computeDueWindow ──────────────────────────────────────────────────────

test("computeDueWindow spans windowDays back to today, in school time", () => {
  const w = computeDueWindow({
    timezone: TZ, windowDays: 14, dueUntil: null, now: new Date("2026-07-29T15:00:00Z"),
  });
  assert.equal(w.today, "2026-07-29");
  assert.equal(w.from, "2026-07-15");
  assert.equal(w.to, "2026-07-29");
});

test("computeDueWindow does not extend past today unless --due-until is later", () => {
  const now = new Date("2026-07-29T15:00:00Z");
  // A past --due-until must never SHRINK the window below today.
  assert.equal(
    computeDueWindow({ timezone: TZ, windowDays: 14, dueUntil: "2026-07-01", now }).to,
    "2026-07-29",
  );
  assert.equal(
    computeDueWindow({ timezone: TZ, windowDays: 14, dueUntil: "2026-08-31", now }).to,
    "2026-08-31",
  );
});

test("computeDueWindow with windowDays 0 is a single school-local day", () => {
  const w = computeDueWindow({
    timezone: TZ, windowDays: 0, dueUntil: null, now: new Date("2026-07-29T15:00:00Z"),
  });
  assert.equal(w.from, "2026-07-29");
  assert.equal(w.to, "2026-07-29");
});

// ── isDueInWindow ─────────────────────────────────────────────────────────

const WINDOW = computeDueWindow({
  timezone: TZ, windowDays: 14, dueUntil: null, now: new Date("2026-07-29T15:00:00Z"),
});

test("isDueInWindow includes both boundary days", () => {
  assert.equal(isDueInWindow("2026-07-15 08:00:00", WINDOW, {}), true, "lower bound");
  assert.equal(isDueInWindow("2026-07-29 08:00:00", WINDOW, {}), true, "upper bound");
});

test("isDueInWindow excludes just outside either boundary", () => {
  assert.equal(isDueInWindow("2026-07-14 23:59:00", WINDOW, {}), false);
  assert.equal(isDueInWindow("2026-07-30 00:01:00", WINDOW, {}), false);
});

test("a late-evening boundary due date survives — the exact DST regression", () => {
  // Under the old +5h shift, 2026-07-15 23:55 became 2026-07-16T04:55Z. That
  // still read as Jul 16 and so passed here, but the same shift pushed the
  // LOWER boundary out of range: a 23:55 assessment on the first day of the
  // window was silently dropped. Both boundaries must now hold exactly.
  assert.equal(isDueInWindow("2026-07-15 23:55:00", WINDOW, {}), true);
  assert.equal(isDueInWindow("2026-07-29 23:55:00", WINDOW, {}), true);
});

test("undated assessments are excluded by default and included with the flag", () => {
  // This is the flag that makes a hand-made test assessment discoverable.
  assert.equal(isDueInWindow(null, WINDOW, {}), false);
  assert.equal(isDueInWindow("", WINDOW, { includeUndated: false }), false);
  assert.equal(isDueInWindow(null, WINDOW, { includeUndated: true }), true);
});

test("a future-dated assessment needs --due-until, which is what the flag is for", () => {
  assert.equal(isDueInWindow("2026-08-15 09:00:00", WINDOW, {}), false);

  const extended = computeDueWindow({
    timezone: TZ, windowDays: 14, dueUntil: "2026-08-31", now: new Date("2026-07-29T15:00:00Z"),
  });
  assert.equal(isDueInWindow("2026-08-15 09:00:00", extended, {}), true);
});

test("an unparseable due date is excluded even with --include-undated", () => {
  // includeUndated means "has no due date", not "has a broken one" — a garbled
  // value must not silently widen the window.
  assert.equal(isDueInWindow("not a date", WINDOW, { includeUndated: true }), false);
});


// ── Storage-key segment safety (wrong-attribution prevention) ──────────────

test("the two-space category literal survives sanitisation untouched", () => {
  // Load-bearing: the backend derives assessment_type by stripping up to the
  // first "-", and the DOUBLE space after "Lesson" flows into every downstream
  // dimension key. Collapsing it forks the dimension.
  const cat = "1 - Lesson  Assessments";
  assert.equal(safeSegment(cat), cat);
  assert.ok(safeSegment(cat).includes("  "), "double space must survive");
});

test("a slash inside any segment is neutralised, not passed through", () => {
  // The parser is positional: a "/" invents a path level and shifts every later
  // segment, landing rows under a wrong subject/grade/section.
  assert.equal(safeSegment("Quizzes/Tests"), "Quizzes_Tests");
  assert.equal(safeSegment("Sec A/B Block"), "Sec A_B Block");
});

test("control characters are stripped but ordinary punctuation is kept", () => {
  assert.equal(safeSegment("Grade 5"), "Grade 5");
  assert.equal(safeSegment("Sec MATH-05A"), "Sec MATH-05A");
});

test("buildRelativePrefix yields exactly 5 segments and a trailing slash", () => {
  const { prefix } = buildRelativePrefix({
    session: "2025-26", category: "1 - Lesson  Assessments",
    subject: "Science", grade: "Grade 2", section: "Sec GAINS Sec 1",
  });
  assert.equal(prefix, "2025-26/1 - Lesson  Assessments/Science/Grade 2/Sec GAINS Sec 1/");
  assert.equal(prefix.split("/").filter(Boolean).length, 5);
});

test("a slash in the CATEGORY cannot add a path level", () => {
  const { prefix, warnings } = buildRelativePrefix({
    session: "2025-26", category: "Quizzes/Tests",
    subject: "Science", grade: "Grade 2", section: "Sec 1",
  });
  assert.equal(prefix.split("/").filter(Boolean).length, 5, "must stay 5 segments");
  assert.match(prefix, /Quizzes_Tests/);
  assert.equal(warnings.length, 1, "the rewrite must be reported, not silent");
});

test("an empty segment is fatal rather than silently collapsing the shape", () => {
  assert.throws(
    () => buildRelativePrefix({
      session: "2025-26", category: "", subject: "Science", grade: "Grade 2", section: "Sec 1",
    }),
    (e) => e.name === "StorageKeyError",
  );
});

test("buildRelativeKey requires a filename", () => {
  const fields = {
    session: "2025-26", category: "C", subject: "S", grade: "G", section: "Sec 1",
  };
  assert.throws(() => buildRelativeKey({ ...fields, filename: "" }), (e) => e.name === "StorageKeyError");
  assert.equal(
    buildRelativeKey({ ...fields, filename: "Question-Data-x.csv" }).key,
    "2025-26/C/S/G/Sec 1/Question-Data-x.csv",
  );
});

// ── academic session, in school time ──────────────────────────────────────

test("academicSession rolls over in August, in the SCHOOL's timezone", () => {
  const TZNY = "America/New_York";
  assert.equal(academicSession(TZNY, new Date("2026-07-31T12:00:00Z")), "2025-26");
  assert.equal(academicSession(TZNY, new Date("2026-08-01T12:00:00Z")), "2026-27");
});

test("academicSession uses school-local date, not the runner's UTC date", () => {
  // 2026-08-01T02:00Z is still 2026-07-31 22:00 in New York, so the school is
  // still in 2025-26. Deriving this from the runner's UTC clock — as the old code
  // did — would file the rows under 2026-27, one segment deep in the storage key.
  const TZNY = "America/New_York";
  assert.equal(academicSession(TZNY, new Date("2026-08-01T02:00:00Z")), "2025-26");
  assert.equal(academicSession("UTC", new Date("2026-08-01T02:00:00Z")), "2026-27");
});


// ── Filename sanitisation (adversarial-review fix) ─────────────────────────

test("a slash in the FILENAME cannot add a path level", () => {
  // Schoology builds the filename from the admin-authored assessment title, so
  // "Unit 3/4 Review" is a realistic input. The backend parser tolerates 7+ parts
  // (it absorbs an interposed category folder), so an unsanitised "/" here
  // MISFILES the rows silently instead of being rejected: subject/grade/section
  // each shift by one.
  const { key, warnings } = buildRelativeKey({
    session: "2025-26", category: "1 - Lesson  Assessments",
    subject: "Science", grade: "Grade 2", section: "Sec 1",
    filename: "Question-Data-Unit 3/4 Review.csv",
  });
  assert.equal(key.split("/").length, 6, "must be exactly 5 segments + filename");
  assert.match(key, /Question-Data-Unit 3_4 Review\.csv$/);
  assert.ok(warnings.some((w) => w.startsWith("filename:")), "the rewrite must be reported");
});

test("a sanitised filename still starts with an ingestable prefix", () => {
  // classify_file_type routes on this prefix; sanitisation must not break it.
  for (const p of ["Question-Data", "Student-Submissions", "Submission-Summary"]) {
    const { key } = buildRelativeKey({
      session: "2025-26", category: "C", subject: "S", grade: "G", section: "Sec 1",
      filename: `${p}-Unit 3/4.csv`,
    });
    assert.ok(key.split("/").pop().startsWith(p), `${p} prefix must survive`);
  }
});

test("a filename that sanitises to nothing is fatal, not silently empty", () => {
  // Only whitespace reduces to empty (safeSegment trims); path characters become
  // underscores, which is safe. Both are asserted so neither behaviour drifts.
  assert.throws(
    () => buildRelativeKey({
      session: "2025-26", category: "C", subject: "S", grade: "G", section: "Sec 1",
      filename: "   ",
    }),
    (e) => e.name === "StorageKeyError",
  );

  // All-slashes is NOT fatal: it becomes "___", which keeps the 5-segments-plus-
  // filename shape intact. That shape is the property the backend depends on.
  const { key } = buildRelativeKey({
    session: "2025-26", category: "C", subject: "S", grade: "G", section: "Sec 1",
    filename: "///",
  });
  assert.equal(key, "2025-26/C/S/G/Sec 1/___");
  assert.equal(key.split("/").length, 6);
});

test("an ordinary filename passes through unchanged and warns about nothing", () => {
  const { key, warnings } = buildRelativeKey({
    session: "2025-26", category: "C", subject: "S", grade: "G", section: "Sec 1",
    filename: "Question-Data-Unit-1-Benchmark-2026-07-30-044639.csv",
  });
  assert.match(key, /Question-Data-Unit-1-Benchmark-2026-07-30-044639\.csv$/);
  assert.deepEqual(warnings, []);
});
