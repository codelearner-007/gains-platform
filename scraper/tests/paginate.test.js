/**
 * Pagination tests (node --test).
 *
 * Each case pins a defect that was live in the hand-rolled walks. The scenarios
 * are modelled on MEASURED behaviour of the Schoology API (2026-07-30, Athenian
 * key), noted per test.
 */
const test = require("node:test");
const assert = require("node:assert/strict");

const { paginate, paginateAll, withParams, normalizeNext } = require("../lib/paginate.js");

/** A fake `get` that serves canned pages and records the URLs requested. */
function fakeApi(pages) {
  const seen = [];
  return {
    seen,
    get: async (url) => {
      seen.push(url);
      if (!(url in pages)) throw new Error(`unexpected request: ${url}`);
      const page = pages[url];
      if (page instanceof Error) throw page;
      return page;
    },
  };
}

// ── withParams / normalizeNext ─────────────────────────────────────────────

test("withParams re-applies caller params, overriding what the URL carried", () => {
  assert.equal(withParams("/courses", { limit: 200 }), "/courses?limit=200");
  assert.equal(
    withParams("/courses?start_id=99&limit=3", { limit: 200, building_id: "186370968" }),
    "/courses?start_id=99&limit=200&building_id=186370968",
  );
});

test("withParams drops empty values instead of emitting limit=", () => {
  assert.equal(withParams("/x", { a: 1, b: "", c: null, d: undefined }), "/x?a=1");
});

test("normalizeNext handles absolute, relative, and /v1-prefixed forms", () => {
  assert.equal(
    normalizeNext("https://api.schoology.com/v1/courses?start_id=5&limit=3"),
    "/courses?start_id=5&limit=3",
  );
  // The relative case is the one the old code mishandled: it passed the value
  // through unchanged, and the caller re-prefixed the /v1 base, producing
  // /v1/v1/courses -> 404 -> null -> silent truncation.
  assert.equal(normalizeNext("/v1/courses?start=20"), "/courses?start=20");
  assert.equal(normalizeNext("courses?start=20"), "/courses?start=20");
  assert.equal(normalizeNext(""), null);
  assert.equal(normalizeNext(undefined), null);
});

// ── the building_id leak ───────────────────────────────────────────────────

test("caller params survive a links.next that dropped them", async () => {
  // MEASURED: /courses?...&building_id=X returns
  //   links.next = "/v1/courses?start_id=204489800&limit=3"   (building_id GONE)
  // Following that verbatim widens page 2+ beyond the requested school.
  const api = fakeApi({
    "/courses?start_id=0&limit=2&building_id=186370968": {
      course: [{ id: 1 }, { id: 2 }],
      links: { next: "https://api.schoology.com/v1/courses?start_id=2&limit=2" },
    },
    "/courses?start_id=2&limit=2&building_id=186370968": {
      course: [{ id: 3 }],
    },
  });

  const res = await paginate({
    get: api.get,
    endpoint: "/courses",
    collection: "course",
    params: { start_id: 0, limit: 2, building_id: "186370968" },
  });

  assert.equal(res.items.length, 3);
  assert.equal(res.pages, 2);
  // The decisive assertion: page 2 was requested WITH the building filter.
  assert.ok(
    api.seen[1].includes("building_id=186370968"),
    `page 2 lost the building filter: ${api.seen[1]}`,
  );
});

// ── truncation paths ───────────────────────────────────────────────────────

test("an empty page mid-walk does NOT end the walk", async () => {
  // The old loops did `if (!data?.x?.length) break` BEFORE reading links.next,
  // so one empty page silently dropped everything after it.
  const api = fakeApi({
    "/x?limit=2": { thing: [{ id: 1 }], links: { next: "/v1/x?page=2&limit=2" } },
    "/x?page=2&limit=2": { thing: [], links: { next: "/v1/x?page=3&limit=2" } },
    "/x?page=3&limit=2": { thing: [{ id: 2 }] },
  });

  const res = await paginate({ get: api.get, endpoint: "/x", collection: "thing", params: { limit: 2 } });
  assert.deepEqual(res.items.map((i) => i.id), [1, 2]);
  assert.equal(res.pages, 3);
});

test("a self-referential links.next terminates instead of looping forever", async () => {
  // Reachable when a redirect drops the query string and the server echoes the
  // same page back — the old code would have spun indefinitely.
  let calls = 0;
  const get = async () => {
    calls += 1;
    if (calls > 10) throw new Error("infinite loop");
    return { thing: [{ id: calls }], links: { next: "/v1/x?limit=2" } };
  };
  const res = await paginate({ get, endpoint: "/x", collection: "thing", params: { limit: 2 } });
  assert.equal(res.pages, 1, "should stop as soon as next repeats a fetched URL");
  assert.equal(calls, 1);
});

test("missing collection key yields an empty result rather than throwing", async () => {
  const api = fakeApi({ "/x?limit=2": { total: 0 } });
  const res = await paginate({ get: api.get, endpoint: "/x", collection: "thing", params: { limit: 2 } });
  assert.deepEqual(res.items, []);
});

// ── the `total` completeness check ─────────────────────────────────────────

test("paginateAll throws when fewer items arrive than the reported total", async () => {
  // MEASURED: /sections and /assignments both report `total` (one real section
  // reported total=323). Ignoring it let a dropped page pass as success.
  const api = fakeApi({
    "/sections/1/assignments?start=0&limit=200": { assignment: [{ id: 1 }], total: 323 },
  });
  await assert.rejects(
    () => paginateAll({
      get: api.get,
      endpoint: "/sections/1/assignments",
      collection: "assignment",
      params: { start: 0, limit: 200 },
    }),
    (err) => {
      assert.equal(err.name, "PaginationError");
      assert.match(err.message, /collected 1 of 323/);
      return true;
    },
  );
});

test("paginateAll accepts a walk that matches the reported total", async () => {
  const api = fakeApi({
    "/sections/1/assignments?start=0&limit=2": {
      assignment: [{ id: 1 }, { id: 2 }], total: 3,
      links: { next: "/v1/sections/1/assignments?start=2&limit=2" },
    },
    "/sections/1/assignments?start=2&limit=2": { assignment: [{ id: 3 }], total: 3 },
  });
  const res = await paginateAll({
    get: api.get,
    endpoint: "/sections/1/assignments",
    collection: "assignment",
    params: { start: 0, limit: 2 },
  });
  assert.equal(res.items.length, 3);
  assert.equal(res.truncated, false);
});

test("no reported total means no assertion — absence is not a shortfall", async () => {
  // MEASURED: /sections/{id}/grading_categories returns neither total nor links.
  const api = fakeApi({ "/sections/1/grading_categories?limit=200": { grading_category: [{ id: 1 }] } });
  const res = await paginateAll({
    get: api.get,
    endpoint: "/sections/1/grading_categories",
    collection: "grading_category",
    params: { limit: 200 },
    expectAll: true,
  });
  assert.equal(res.items.length, 1);
  assert.equal(res.total, null);
  assert.equal(res.truncated, false);
});

test("expectAll still follows links.next, and warns, rather than truncating", async () => {
  const warnings = [];
  const api = fakeApi({
    "/sections/1/grading_categories?limit=200": {
      grading_category: [{ id: 1 }],
      links: { next: "/v1/sections/1/grading_categories?page=2&limit=200" },
    },
    "/sections/1/grading_categories?page=2&limit=200": { grading_category: [{ id: 2 }] },
  });
  const res = await paginate({
    get: api.get,
    endpoint: "/sections/1/grading_categories",
    collection: "grading_category",
    params: { limit: 200 },
    expectAll: true,
    log: { warn: (m) => warnings.push(m), debug() {}, info() {} },
  });
  assert.equal(res.items.length, 2, "must not truncate an endpoint that unexpectedly paginates");
  assert.ok(warnings.some((w) => /assumed unpaginated/.test(w)), "should warn about the broken assumption");
});

test("a hard error from get propagates — it is never swallowed into a short list", async () => {
  const api = fakeApi({ "/x?limit=2": new Error("HTTP 500") });
  await assert.rejects(
    () => paginate({ get: api.get, endpoint: "/x", collection: "thing", params: { limit: 2 } }),
    /HTTP 500/,
  );
});


// ── Early termination must be VISIBLE and FATAL (adversarial-review fix) ────

test("a null body mid-collection is a hard error, not end-of-collection", async () => {
  // apiGet returns null for HTTP 404. On page 2+ that means a page of a
  // collection we were walking vanished. Previously this ended the walk with
  // truncated=false (no `total` to compare against) and paginateAll RESOLVED —
  // a short list indistinguishable from a complete one.
  const api = fakeApi({
    "/x?limit=2": { thing: [{ id: 1 }], links: { next: "/v1/x?page=2&limit=2" } },
    "/x?page=2&limit=2": null,
  });
  const res = await paginate({ get: api.get, endpoint: "/x", collection: "thing", params: { limit: 2 } });
  assert.equal(res.stoppedEarly, "null-response");

  const api2 = fakeApi({
    "/x?limit=2": { thing: [{ id: 1 }], links: { next: "/v1/x?page=2&limit=2" } },
    "/x?page=2&limit=2": null,
  });
  await assert.rejects(
    () => paginateAll({ get: api2.get, endpoint: "/x", collection: "thing", params: { limit: 2 } }),
    (err) => {
      assert.equal(err.name, "PaginationError");
      assert.match(err.message, /null-response/);
      return true;
    },
  );
});

test("a null body on the FIRST page is a legitimate empty collection", async () => {
  // A deleted/absent collection 404s immediately; that is not a truncated walk.
  const api = fakeApi({ "/x?limit=2": null });
  const res = await paginateAll({ get: api.get, endpoint: "/x", collection: "thing", params: { limit: 2 } });
  assert.deepEqual(res.items, []);
  assert.equal(res.stoppedEarly, null);
});

test("a repeated links.next is reported as stoppedEarly and rejected by paginateAll", async () => {
  const get = async () => ({ thing: [{ id: 1 }], links: { next: "/v1/x?limit=2" } });
  const res = await paginate({ get, endpoint: "/x", collection: "thing", params: { limit: 2 } });
  assert.equal(res.stoppedEarly, "repeat-url");
  await assert.rejects(
    () => paginateAll({ get, endpoint: "/x", collection: "thing", params: { limit: 2 } }),
    /repeat-url/,
  );
});

test("a complete walk reports stoppedEarly = null", async () => {
  const api = fakeApi({ "/x?limit=2": { thing: [{ id: 1 }] } });
  const res = await paginateAll({ get: api.get, endpoint: "/x", collection: "thing", params: { limit: 2 } });
  assert.equal(res.stoppedEarly, null);
});
