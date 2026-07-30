/**
 * The Dockerfile's Playwright base-image tag MUST equal the playwright version
 * that `npm ci` actually installs.
 *
 * Each Playwright release pins its own browser revisions under /ms-playwright, so
 * a mismatch produces a container that builds fine, passes `npm ci`, and then dies
 * on the FIRST scrape with "Executable doesn't exist at
 * /ms-playwright/chromium-<rev>". That is exactly what shipped once already: base
 * `v1.49.0-jammy` against a lockfile pinning 1.61.1.
 *
 * The Dockerfile explains this invariant in a comment. A comment cannot fail, so
 * this test does — turning a first-scrape-only runtime failure into a red suite.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");

function dockerfileBaseTag() {
  const df = fs.readFileSync(path.join(ROOT, "Dockerfile"), "utf8");
  const m = df.match(/^FROM\s+mcr\.microsoft\.com\/playwright:v(\S+)$/m);
  assert.ok(m, "could not find a Playwright FROM line in scraper/Dockerfile");
  return m[1]; // e.g. "1.61.1-noble"
}

function lockedPlaywrightVersion() {
  const lock = JSON.parse(fs.readFileSync(path.join(ROOT, "package-lock.json"), "utf8"));
  const entry = lock.packages?.["node_modules/playwright"];
  assert.ok(entry?.version, "playwright not found in package-lock.json");
  return entry.version; // e.g. "1.61.1"
}

test("Dockerfile base image matches the locked playwright version", () => {
  const tag = dockerfileBaseTag();
  const locked = lockedPlaywrightVersion();
  const tagVersion = tag.split("-")[0];
  assert.equal(
    tagVersion, locked,
    `scraper/Dockerfile is FROM …playwright:v${tag} but package-lock.json installs `
    + `playwright ${locked}. Chromium would be missing at runtime — bump both together.`,
  );
});

test("package.json's playwright range admits the locked version", () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8"));
  const declared = pkg.dependencies.playwright;
  const locked = lockedPlaywrightVersion();
  // Only the caret-minor form is used here; a full semver range check would need a
  // dependency, and the point is just to catch package.json and the lock drifting.
  const [dMajor, dMinor] = declared.replace(/^[^\d]*/, "").split(".").map(Number);
  const [lMajor, lMinor] = locked.split(".").map(Number);
  assert.equal(lMajor, dMajor, `package.json wants ${declared}, lock has ${locked}`);
  assert.ok(lMinor >= dMinor, `package.json wants ${declared}, lock has ${locked}`);
});

test("the base image is a Node >= 22 variant", () => {
  // @supabase/* declares engines node>=22; the jammy variants of this era ship
  // Node 20. Verified in-container: noble ships v24.
  const tag = dockerfileBaseTag();
  const distro = tag.split("-").slice(1).join("-");
  assert.ok(
    ["noble", "resolute"].includes(distro),
    `base image distro "${distro}" may ship Node < 22, which @supabase/* rejects`,
  );
});


/**
 * A Railway deploy RUNS the container. So a start command that scrapes means every
 * deploy performs a live export — which is exactly what happened once: a
 * `startCommand` of `node schoology-exporter.js --school Athenian` turned the
 * service's first deploy into a production run against real student data.
 *
 * Overriding it to something safe at the service level does not help: this file
 * takes precedence over the dashboard/API setting. So the committed value is the
 * only thing that decides, and it is asserted here.
 */
test("railway.json's start command cannot trigger a scrape", () => {
  const cfg = JSON.parse(fs.readFileSync(path.join(ROOT, "railway.json"), "utf8"));
  const cmd = cfg.deploy.startCommand;

  for (const flag of ["--school", "--assessment", "--due-until", "--include-undated"]) {
    assert.ok(
      !cmd.includes(flag),
      `startCommand contains ${flag} — every deploy of this service would scrape. `
      + `Keep it inert and invoke runs with \`railway run\`. If enabling cron, that is `
      + `a deliberate, reviewable change (see DEPLOY.md) — update this test with it.`,
    );
  }
  // Positively assert the inert form, so silently emptying the command also fails.
  assert.match(cmd, /--help$/, "the inert start command should be `--help`");
});

test("a one-shot job must never be auto-restarted", () => {
  // The scraper exits non-zero on partial failure. ON_FAILURE would restart it into
  // a full re-export: hammering Schoology and duplicating objects in the bucket.
  const cfg = JSON.parse(fs.readFileSync(path.join(ROOT, "railway.json"), "utf8"));
  assert.equal(cfg.deploy.restartPolicyType, "NEVER");
});
