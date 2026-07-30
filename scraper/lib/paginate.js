/**
 * One paginator for every Schoology collection read.
 *
 * There were four hand-rolled walks in the exporter and each had a different
 * subset of the same bugs. Every defect below was either measured against the
 * live API or read out of the code; none is hypothetical.
 *
 * MEASURED FACTS (live API, Athenian key, 2026-07-30):
 *   - `/courses?...&building_id=X` returns `links.next` with **building_id
 *     STRIPPED**: next = `/v1/courses?start_id=204489800&limit=3`. Following it
 *     verbatim silently widens the query beyond the requested school. (Harmless
 *     today only because this key sees exactly one building — scoped and
 *     unscoped both return 106 courses — but the code comment at the call site
 *     states the key is shared, and a shared key WOULD leak.)
 *   - `/courses/{id}/sections` sends no limit and defaults to **limit=20**,
 *     and returns `total`. The old code read neither, so a course with >20
 *     sections silently lost the rest — and with them every assessment in them.
 *   - `/sections/{id}/assignments` also defaults to limit=20 and returns
 *     `total` (one real section reported **total=323**). With limit=200 +
 *     links.next it collects 323/323 correctly.
 *   - `/sections/{id}/grading_categories` returns NO `total` and NO `links`,
 *     which is evidence it is unpaginated — but only observed on a 4-category
 *     section, so it cannot be proven for large sets. Hence `expectAll`.
 *
 * WHAT THIS FIXES
 *   1. **Param loss** — the caller's query params (building_id, limit) are
 *      re-applied to every page, so a stripped `links.next` cannot widen scope.
 *   2. **Relative next** — the old code only rewrote `links.next` when it
 *      startsWith("http"); a relative value was re-prefixed with the /v1 base
 *      producing `/v1/v1/courses` → 404 → null → silent break.
 *   3. **Empty-page break** — the old loops did `if (!data?.x?.length) break`
 *      BEFORE consulting links.next, so one empty page mid-walk truncated the
 *      rest.
 *   4. **Infinite loops** — a `links.next` that echoes the current URL (which
 *      happens when a redirect drops the query string) span forever. Now every
 *      visited URL is remembered and a repeat ends the walk.
 *   5. **Silent truncation** — when the server reports `total`, the collected
 *      count is asserted against it and a shortfall THROWS instead of returning
 *      a quietly short list.
 */

const DEFAULT_PAGE_LIMIT = 200;
const MAX_PAGES = 200; // 200 pages x 200 rows = 40k items; a runaway guard, not a real bound.

/**
 * Merge `params` into `url`'s query string.
 *
 * `mode: "override"` — params win. Used for the FIRST page, where the caller's
 *   values are authoritative.
 * `mode: "fill"` — the URL wins and params only supply keys the URL lacks. Used
 *   for every subsequent page.
 *
 * The distinction is essential and was got wrong first time round: `links.next`
 * carries the CURSOR (`start_id` / `start`) advanced by the server. Overriding
 * that with the caller's original `start_id=0` rewinds the walk to page 1 — which
 * the loop-guard then detects as a repeat and stops, silently returning only the
 * first page. "Fill" restores the dropped FILTER (building_id) while leaving the
 * cursor alone.
 */
function withParams(pathAndQuery, params, mode = "override") {
  const [path, query = ""] = String(pathAndQuery).split("?");
  const sp = new URLSearchParams(query);
  for (const [k, v] of Object.entries(params || {})) {
    if (v === undefined || v === null || v === "") continue;
    if (mode === "fill" && sp.has(k)) continue;
    sp.set(k, String(v));
  }
  const qs = sp.toString();
  return qs ? `${path}?${qs}` : path;
}

/** Normalise a `links.next` value to a /v1-relative "path?query" string. */
function normalizeNext(next) {
  if (!next) return null;
  const raw = String(next).trim();
  if (!raw) return null;
  if (/^https?:\/\//i.test(raw)) {
    const u = new URL(raw);
    // Strip the /v1 prefix — callers pass /v1-relative endpoints.
    return u.pathname.replace(/^\/v1/, "") + (u.search || "");
  }
  // Relative form. Strip a leading /v1 if present so we cannot produce /v1/v1/…
  const withSlash = raw.startsWith("/") ? raw : `/${raw}`;
  return withSlash.replace(/^\/v1/, "");
}

/**
 * Walk a paginated Schoology collection to completion.
 *
 * @param {object}   o
 * @param {function} o.get          async (endpoint) => parsed JSON (throws on hard failure)
 * @param {string}   o.endpoint     /v1-relative first page, e.g. "/courses"
 * @param {string}   o.collection   response key holding the array, e.g. "course"
 * @param {object}   [o.params]     query params re-applied to EVERY page
 * @param {boolean}  [o.expectAll]  true => the endpoint is believed unpaginated;
 *                                  warn if a `links.next` unexpectedly appears
 * @param {object}   [o.log]        logger
 * @returns {Promise<{items: any[], pages: number, total: number|null, truncated: boolean}>}
 */
async function paginate({ get, endpoint, collection, params = {}, expectAll = false, log = null }) {
  // Default the page size IN the mechanism. Every one of these endpoints silently
  // defaults to limit=20 server-side, which is the whole reason this module exists —
  // leaving the default at the call sites meant a future caller that forgot `limit`
  // would quietly reinstate the original truncation bug.
  if (params.limit === undefined || params.limit === null || params.limit === "") {
    params = { ...params, limit: DEFAULT_PAGE_LIMIT };
  }
  const items = [];
  const seen = new Set();
  let url = withParams(endpoint, params);
  let pages = 0;
  let total = null;
  // Why a reason code and not just `truncated`: `truncated` can only be computed
  // when the endpoint reports `total`, and grading_categories provably does not.
  // Without this, a walk that died mid-collection resolved as a complete short
  // list — the exact silent truncation this module exists to prevent.
  let stoppedEarly = null;

  while (url) {
    if (seen.has(url)) {
      // A links.next that points at a page we already fetched. Ending the walk
      // is correct: continuing would loop forever.
      log?.warn("pagination stopped: links.next repeated an already-fetched page", {
        endpoint, url, pages, collected: items.length,
      });
      stoppedEarly = "repeat-url";
      break;
    }
    seen.add(url);

    const data = await get(url);
    pages += 1;

    // A null/undefined body is how the caller signals HTTP 404. On the FIRST page
    // that legitimately means "no such collection"; from page 2 onward it means a
    // page of a collection we were mid-way through vanished, which must not be
    // mistaken for the end.
    if (data === null || data === undefined) {
      if (pages > 1) {
        log?.warn("pagination stopped: a page returned no body mid-collection", {
          endpoint, url, pages, collected: items.length,
        });
        stoppedEarly = "null-response";
      }
      break;
    }

    // A MISSING collection key is a legitimate empty page. A key that is present
     // but NOT an array means the response shape changed under us, and silently
     // reading it as empty would look identical to "no results".
    if (data && data[collection] !== undefined && !Array.isArray(data[collection])) {
      log?.warn("collection key is present but not an array — response shape changed?", {
        endpoint, collection, actualType: typeof data[collection],
      });
    }
    const batch = Array.isArray(data?.[collection]) ? data[collection] : [];
    items.push(...batch);
    // Keep the FIRST usable total and ignore NaN. Overwriting per page let the
    // last page win, and `Number("")`/`Number(null)` would have quietly disabled
    // the completeness assertion by making it NaN.
    if (total === null && data && data.total !== undefined && data.total !== null) {
      const parsed = Number(data.total);
      if (Number.isFinite(parsed)) total = parsed;
      else log?.warn("ignoring non-numeric `total` from Schoology", { endpoint, total: data.total });
    }

    if (expectAll && data?.links?.next) {
      // The endpoint was assumed unpaginated. Do not silently truncate — follow
      // it and say so, loudly, because the assumption is now known to be wrong.
      log?.warn("endpoint assumed unpaginated returned links.next — following it", {
        endpoint, collected: items.length,
      });
    }

    const next = normalizeNext(data?.links?.next);
    // NOTE: an empty batch does NOT end the walk. The old loops broke on the
    // first empty page, so a single empty page mid-collection truncated the rest.
    if (!next) break;

    if (pages >= MAX_PAGES) {
      log?.warn("pagination hit the page cap — collection may be incomplete", {
        endpoint, pages, collected: items.length, total,
      });
      stoppedEarly = "page-cap";
      break;
    }

    // Restore filters the server dropped (building_id) WITHOUT touching the
    // cursor the server advanced — hence "fill", not "override".
    url = withParams(next, params, "fill");
  }

  const truncated = total !== null && items.length < total;
  return { items, pages, total, truncated, stoppedEarly };
}

/**
 * paginate() + a hard completeness assertion.
 *
 * When the server tells us `total`, a shortfall is a real defect (a dropped
 * page, a silent 404 mid-walk) and must fail the school rather than proceed with
 * a partial assessment set — a partial set produces a run that reports success
 * while quietly missing sections.
 */
async function paginateAll(opts) {
  const result = await paginate(opts);

  // Two independent completeness checks. The count check only works when the
  // endpoint reports `total`; the reason check works always, which is what covers
  // the endpoints that report nothing.
  if (result.stoppedEarly) {
    const err = new Error(
      `incomplete pagination for ${opts.endpoint}: walk ended early `
      + `(${result.stoppedEarly}) after ${result.pages} page(s) with ${result.items.length} item(s)`,
    );
    err.name = "PaginationError";
    throw err;
  }
  if (result.truncated) {
    const err = new Error(
      `incomplete pagination for ${opts.endpoint}: collected ${result.items.length} of `
      + `${result.total} reported by Schoology after ${result.pages} page(s)`,
    );
    err.name = "PaginationError";
    throw err;
  }
  return result;
}

module.exports = { paginate, paginateAll, withParams, normalizeNext, DEFAULT_PAGE_LIMIT, MAX_PAGES };
