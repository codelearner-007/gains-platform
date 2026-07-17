/**
 * Run `fn` over `items` with at most `limit` promises in flight at once,
 * preserving input order in the results array. Used by the admin bulk routes
 * (invite / bulk user actions) so N Supabase admin calls complete in a few×
 * single latency instead of N×, without hammering the upstream all at once.
 */
export async function mapPool<T, R>(
  items: T[],
  limit: number,
  fn: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  const results = new Array<R>(items.length);
  let cursor = 0;
  async function worker() {
    while (cursor < items.length) {
      const idx = cursor++;
      results[idx] = await fn(items[idx], idx);
    }
  }
  await Promise.all(
    Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, worker),
  );
  return results;
}
