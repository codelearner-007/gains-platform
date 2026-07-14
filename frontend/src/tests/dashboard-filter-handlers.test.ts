import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';

// Regression guard: a styling pass once silently deleted the SubjectKpiCards
// `onClick` (replaced by `style={...}` in the same hunk) — subject filtering
// became a no-op with NO type/lint error, since an unused destructured prop is
// legal. There is no RTL/jsdom harness in this project, so this asserts the
// handler wiring at the source level: each front filter control must invoke its
// `onSelect` from an `onClick`.
const dir = dirname(fileURLToPath(import.meta.url));
const dashboard = join(dir, '..', 'components', 'app', 'dashboard');
const read = (f: string) => readFileSync(join(dashboard, f), 'utf8');

describe('dashboard front-filter click handlers are wired', () => {
  it('SubjectKpiCards calls onSelect from an onClick', () => {
    const src = read('SubjectKpiCards.tsx');
    expect(src).toMatch(/onClick=\{[^}]*onSelect\(/);
  });

  it('GradeChips calls onSelect from an onClick', () => {
    const src = read('GradeChips.tsx');
    expect(src).toMatch(/onClick=\{[^}]*onSelect\(/);
  });
});
