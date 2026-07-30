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
