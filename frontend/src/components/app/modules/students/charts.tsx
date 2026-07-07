'use client';

import { useRef, useState, type ReactNode } from 'react';
import type { PerfBandName } from '@/lib/reports/types';
import { BRAND, bandFill, bandLabel, bandTone } from './bands';

const clamp = (v: number, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, v));
const pctStr = (v: number | null) => (v === null ? '—' : `${v.toFixed(1)}%`);

/* ───────────────────────── hover tooltip plumbing ──────────────────────── */

interface TipState {
  left: number;
  top: number;
  content: ReactNode;
}

/** A styled, positioned tooltip anchored to a chart element (mouse + keyboard).
 *  Print-hidden so exported PDFs stay static documents. */
function useTip() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [tip, setTip] = useState<TipState | null>(null);
  const show = (el: Element, content: ReactNode) => {
    const c = ref.current?.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    if (!c) return;
    setTip({ left: r.left + r.width / 2 - c.left, top: r.top - c.top, content });
  };
  return { ref, tip, show, hide: () => setTip(null) };
}

function Tip({ tip }: { tip: TipState | null }) {
  if (!tip) return null;
  return (
    <div
      role="status"
      className="pointer-events-none absolute z-30 max-w-[220px] -translate-x-1/2 -translate-y-full rounded-md border px-2.5 py-1.5 text-[11px] leading-snug shadow-lg print:hidden"
      style={{ left: tip.left, top: tip.top - 7, background: BRAND.paper, borderColor: BRAND.hair, color: BRAND.ink }}
    >
      {tip.content}
    </div>
  );
}

/** Reusable tooltip body: a bold heading + label/value rows. */
export function TipBody({ heading, rows }: { heading: string; rows: [string, string, string?][] }) {
  return (
    <div className="whitespace-nowrap">
      <div className="mb-0.5 font-semibold" style={{ color: BRAND.navy }}>{heading}</div>
      {rows.map(([k, v, color]) => (
        <div key={k} className="flex items-center justify-between gap-3">
          <span style={{ color: BRAND.muted }}>{k}</span>
          <span className="font-medium tabular-nums" style={{ color: color || BRAND.ink }}>{v}</span>
        </div>
      ))}
    </div>
  );
}

const focusable = {
  tabIndex: 0,
  style: { cursor: 'pointer', outline: 'none' } as const,
};

/* ───────────────────────────── score ring ─────────────────────────────── */

export function ScoreRing({
  pct,
  band,
  classPct,
  size = 132,
  label = 'Overall',
}: {
  pct: number | null;
  band: PerfBandName;
  classPct?: number | null;
  size?: number;
  label?: string;
}) {
  const { ref, tip, show, hide } = useTip();
  const stroke = size * 0.1;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = pct === null ? 0 : clamp(pct);
  const dash = (v / 100) * c;
  const cx = size / 2;
  const delta = pct !== null && classPct != null ? pct - classPct : null;
  const content = (
    <TipBody
      heading={`${label} score`}
      rows={[
        ['Student', pctStr(pct), bandFill(band)],
        ...(classPct != null ? ([['Class avg', pctStr(classPct)]] as [string, string][]) : []),
        ...(delta != null ? ([['vs class', `${delta >= 0 ? '+' : ''}${delta.toFixed(1)} pts`]] as [string, string][]) : []),
      ]}
    />
  );
  return (
    <div ref={ref} className="relative inline-block">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img"
        aria-label={`Overall score ${pct === null ? 'not available' : `${pct.toFixed(1)} percent`}`}>
        <circle cx={cx} cy={cx} r={r} fill="none" stroke={BRAND.hair} strokeWidth={stroke} />
        {pct !== null && (
          <circle
            {...focusable}
            cx={cx} cy={cx} r={r} fill="none" stroke={bandFill(band)} strokeWidth={stroke}
            strokeLinecap="round" strokeDasharray={`${dash} ${c - dash}`} transform={`rotate(-90 ${cx} ${cx})`}
            onMouseEnter={(e) => show(e.currentTarget, content)} onMouseLeave={hide}
            onFocus={(e) => show(e.currentTarget, content)} onBlur={hide}
          >
            <title>{`${label}: ${pctStr(pct)}${classPct != null ? ` (class ${pctStr(classPct)})` : ''}`}</title>
          </circle>
        )}
        <text x={cx} y={cx - 2} textAnchor="middle" dominantBaseline="central"
          style={{ fontSize: size * 0.24, fontWeight: 700, fill: BRAND.navy }}>
          {pct === null ? '—' : Math.round(pct)}
          {pct !== null && <tspan style={{ fontSize: size * 0.12, fill: BRAND.muted }}>%</tspan>}
        </text>
        <text x={cx} y={cx + size * 0.18} textAnchor="middle"
          style={{ fontSize: size * 0.085, letterSpacing: 0.5, fill: BRAND.muted, textTransform: 'uppercase' }}>
          {label}
        </text>
      </svg>
      <Tip tip={tip} />
    </div>
  );
}

/* ───────────────────────────────── radar ──────────────────────────────── */

export interface RadarAxis {
  label: string; // already disambiguated by the caller
  value: number | null;
  classValue: number | null;
}

/** Split a label into ≤2 lines so long/duplicate subject names never truncate. */
function wrap(label: string): string[] {
  if (label.length <= 12) return [label];
  const words = label.split(' ');
  if (words.length === 1) return [label.slice(0, 11) + '…'];
  const mid = Math.ceil(words.length / 2);
  return [words.slice(0, mid).join(' '), words.slice(mid).join(' ')];
}

export function Radar({ axes, size = 300 }: { axes: RadarAxis[]; size?: number }) {
  const { ref, tip, show, hide } = useTip();
  const cx = size / 2;
  const cy = size / 2;
  const R = size * 0.3; // leaves generous room for labels — no truncation
  const n = Math.max(axes.length, 3);
  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2;
  const pt = (i: number, radius: number): [number, number] => [cx + radius * Math.cos(angle(i)), cy + radius * Math.sin(angle(i))];
  const poly = (vals: (number | null)[]) => vals.map((val, i) => pt(i, (clamp(val ?? 0) / 100) * R).join(',')).join(' ');
  const rings = [0.25, 0.5, 0.75, 1];

  return (
    <div ref={ref} className="relative inline-block">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img"
        style={{ overflow: 'visible' }}
        aria-label="Subject performance radar, student versus class average">
        {rings.map((f, i) => (
          <polygon key={i} points={axes.map((_, j) => pt(j, R * f).join(',')).join(' ')}
            fill="none" stroke={i === rings.length - 1 ? BRAND.hair : BRAND.hairSoft} />
        ))}
        {axes.map((_, i) => { const [x, y] = pt(i, R); return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke={BRAND.hairSoft} />; })}
        {/* ring scale label on the vertical axis (context for the grid) */}
        <text x={cx + 3} y={cy - R * 0.75} style={{ fontSize: size * 0.036, fill: BRAND.faint }}>80</text>
        {/* class (dashed brass) then student (navy translucent) */}
        <polygon points={poly(axes.map((a) => a.classValue))} fill="none" stroke={BRAND.brassBright} strokeWidth={1.5} strokeDasharray="4 3" />
        <polygon points={poly(axes.map((a) => a.value))} fill={`${BRAND.navySoft}22`} stroke={BRAND.navy} strokeWidth={2} />
        {/* interactive student vertices */}
        {axes.map((a, i) => {
          const [x, y] = pt(i, (clamp(a.value ?? 0) / 100) * R);
          const content = <TipBody heading={a.label} rows={[['Student', pctStr(a.value), BRAND.navy], ['Class avg', pctStr(a.classValue), BRAND.brass]]} />;
          return (
            <circle key={i} {...focusable} cx={x} cy={y} r={4} fill={BRAND.paper} stroke={BRAND.navy} strokeWidth={2}
              onMouseEnter={(e) => show(e.currentTarget, content)} onMouseLeave={hide}
              onFocus={(e) => show(e.currentTarget, content)} onBlur={hide} aria-label={`${a.label}: ${pctStr(a.value)}`}>
              <title>{`${a.label}: ${pctStr(a.value)} (class ${pctStr(a.classValue)})`}</title>
            </circle>
          );
        })}
        {/* axis labels — wrapped, anchored by side, never truncated */}
        {axes.map((a, i) => {
          const [lx, ly] = pt(i, R + size * 0.055);
          const anchor = Math.abs(lx - cx) < 8 ? 'middle' : lx > cx ? 'start' : 'end';
          const lines = wrap(a.label);
          return (
            <text key={i} x={lx} y={ly - (lines.length - 1) * size * 0.024} textAnchor={anchor} dominantBaseline="central"
              style={{ fontSize: size * 0.042, fill: BRAND.ink, fontWeight: 500 }}>
              <title>{a.label}</title>
              {lines.map((ln, k) => (<tspan key={k} x={lx} dy={k === 0 ? 0 : size * 0.048}>{ln}</tspan>))}
            </text>
          );
        })}
      </svg>
      <Tip tip={tip} />
    </div>
  );
}

/* ───────────────────────────── bullet bar ─────────────────────────────── */

/** A shared 0–100 scale rule with the 80% target marked — render once above a group. */
export function BulletScale({ target = 80 }: { target?: number }) {
  return (
    <div className="relative h-4 select-none text-[9.5px]" style={{ color: BRAND.faint }} aria-hidden>
      <span className="absolute left-0">0</span>
      <span className="absolute -translate-x-1/2" style={{ left: `${target}%`, color: BRAND.brass }}>{target}</span>
      <span className="absolute right-0">100</span>
    </div>
  );
}

export function BulletBar({
  value,
  classValue,
  band,
  label,
  target = 80,
  height = 18,
}: {
  value: number | null;
  classValue: number | null;
  band: PerfBandName;
  label?: string;
  target?: number;
  height?: number;
}) {
  const { ref, tip, show, hide } = useTip();
  const w = 100;
  const v = value === null ? 0 : clamp(value);
  const content = (
    <TipBody
      heading={label ?? 'Score'}
      rows={[
        ['Student', pctStr(value), bandFill(band)],
        ['Class avg', pctStr(classValue), BRAND.brass],
        ['Target', `${target}%`],
      ]}
    />
  );
  return (
    <div ref={ref} className="relative">
      <svg width="100%" height={height} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" role="img"
        aria-label={`${label ? label + ': ' : ''}${pctStr(value)}${classValue !== null ? `, class ${pctStr(classValue)}` : ''}, target ${target}%`}
        onMouseMove={(e) => show(e.currentTarget, content)} onMouseLeave={hide}
        onFocus={(e) => show(e.currentTarget, content)} onBlur={hide} {...focusable}>
        <title>{`${label ? label + ': ' : ''}${pctStr(value)} (class ${pctStr(classValue)}, target ${target}%)`}</title>
        <rect x={0} y={0} width={w} height={height} rx={2} fill={BRAND.hairSoft} />
        <rect x={target} y={0} width={w - target} height={height} fill={`${BRAND.brassBright}14`} />
        {value !== null && <rect x={0} y={0} width={v} height={height} rx={2} fill={bandFill(band)} />}
        <line x1={target} y1={-1} x2={target} y2={height + 1} stroke={BRAND.brass} strokeWidth={0.8} strokeDasharray="2 1.5" />
        {classValue !== null && (
          <line x1={clamp(classValue)} y1={1} x2={clamp(classValue)} y2={height - 1} stroke={BRAND.navy} strokeWidth={1.6} />
        )}
      </svg>
      <Tip tip={tip} />
    </div>
  );
}

/* ───────────────────────────── trend line ─────────────────────────────── */

export interface TrendPoint {
  label: string;
  date?: string | null;
  value: number | null;
  classValue: number | null;
}

export function TrendLine({ points, width = 340, height = 128 }: { points: TrendPoint[]; width?: number; height?: number }) {
  const { ref, tip, show, hide } = useTip();
  const padL = 24; // room for y-axis labels
  const padR = 8;
  const padT = 10;
  const padB = 16; // room for x baseline
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;
  const n = points.length;
  const x = (i: number) => padL + (n <= 1 ? innerW / 2 : (innerW * i) / (n - 1));
  const y = (v: number) => padT + innerH - (clamp(v) / 100) * innerH;
  const path = (key: 'value' | 'classValue') => {
    const segs: string[] = [];
    points.forEach((p, i) => { const v = p[key]; if (v === null) return; segs.push(`${segs.length === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`); });
    return segs.join(' ');
  };
  const yTicks = [0, 50, 80, 100];
  return (
    <div ref={ref} className="relative">
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Score trend across assessments, student solid versus class dashed">
        {/* y grid + labels */}
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={padL} y1={y(t)} x2={width - padR} y2={y(t)} stroke={t === 80 ? BRAND.brassBright : BRAND.hairSoft} strokeWidth={t === 80 ? 1 : 0.6} strokeDasharray={t === 80 ? '3 2' : undefined} />
            <text x={padL - 4} y={y(t)} textAnchor="end" dominantBaseline="central" style={{ fontSize: 8, fill: t === 80 ? BRAND.brass : BRAND.faint }}>{t}</text>
          </g>
        ))}
        {/* x baseline */}
        <line x1={padL} y1={y(0)} x2={width - padR} y2={y(0)} stroke={BRAND.hair} strokeWidth={0.8} />
        <text x={width - padR} y={height - 3} textAnchor="end" style={{ fontSize: 8, fill: BRAND.faint }}>assessments →</text>
        <path d={path('classValue')} fill="none" stroke={BRAND.brassBright} strokeWidth={1.4} strokeDasharray="4 3" />
        <path d={path('value')} fill="none" stroke={BRAND.navy} strokeWidth={2} strokeLinejoin="round" />
        {points.map((p, i) => p.value === null ? null : (
          <circle key={i} {...focusable} cx={x(i)} cy={y(p.value)} r={n > 24 ? 2 : 3} fill={BRAND.paper} stroke={BRAND.navy} strokeWidth={1.6}
            onMouseEnter={(e) => show(e.currentTarget, <TipBody heading={p.label} rows={[...(p.date ? ([['Date', p.date]] as [string, string][]) : []), ['Student', pctStr(p.value), BRAND.navy], ['Class avg', pctStr(p.classValue), BRAND.brass]]} />)}
            onMouseLeave={hide}
            onFocus={(e) => show(e.currentTarget, <TipBody heading={p.label} rows={[['Student', pctStr(p.value), BRAND.navy], ['Class avg', pctStr(p.classValue), BRAND.brass]]} />)}
            onBlur={hide} aria-label={`${p.label}: ${pctStr(p.value)}`}>
            <title>{`${p.label}${p.date ? ` (${p.date})` : ''}: ${pctStr(p.value)}`}</title>
          </circle>
        ))}
      </svg>
      <Tip tip={tip} />
    </div>
  );
}

/* ──────────────────────── mastery distribution bar ─────────────────────── */

export function MasteryBar({ green, yellow, pink, height = 16 }: { green: number; yellow: number; pink: number; height?: number }) {
  const { ref, tip, show, hide } = useTip();
  const total = green + yellow + pink;
  if (total === 0) return <div style={{ height, background: BRAND.hairSoft, borderRadius: 3 }} aria-label="No standards" />;
  const seg = (n: number, band: PerfBandName, name: string) =>
    n > 0 ? (
      <div {...focusable} style={{ width: `${(n / total) * 100}%`, background: bandFill(band), height }}
        onMouseEnter={(e) => show(e.currentTarget, <TipBody heading={name} rows={[['Standards', String(n)], ['Share', `${((n / total) * 100).toFixed(0)}%`]]} />)}
        onMouseLeave={hide} onFocus={(e) => show(e.currentTarget, <TipBody heading={name} rows={[['Standards', String(n)]]} />)} onBlur={hide}
        aria-label={`${name}: ${n} standards`} title={`${name}: ${n}`} />
    ) : null;
  return (
    <div ref={ref} className="relative">
      <div style={{ display: 'flex', height, borderRadius: 3, overflow: 'hidden', border: `1px solid ${BRAND.hair}` }}>
        {seg(green, 'green', bandLabel('green'))}
        {seg(yellow, 'yellow', bandLabel('yellow'))}
        {seg(pink, 'pink', bandLabel('pink'))}
      </div>
      <Tip tip={tip} />
    </div>
  );
}

/* ─────────────────────── mastery donut (proportion) ───────────────────── */

export function Donut({
  segments,
  centerValue,
  centerLabel,
  size = 148,
}: {
  segments: { value: number; band: PerfBandName; name: string }[];
  centerValue: number | string;
  centerLabel?: string;
  size?: number;
}) {
  const { ref, tip, show, hide } = useTip();
  const stroke = size * 0.15;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const cx = size / 2;
  const sum = segments.reduce((s, x) => s + x.value, 0) || 1;
  return (
    <div ref={ref} className="relative inline-block">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Standards mastery distribution">
        <circle cx={cx} cy={cx} r={r} fill="none" stroke={BRAND.hairSoft} strokeWidth={stroke} />
        {segments.map((s, i) => {
          if (s.value <= 0) return null;
          const frac = s.value / sum;
          const dash = frac * c;
          const off = (segments.slice(0, i).reduce((a, x) => a + x.value, 0) / sum) * c;
          const content = <TipBody heading={s.name} rows={[['Standards', String(s.value)], ['Share', `${Math.round(frac * 100)}%`]]} />;
          return (
            <circle key={i} {...focusable} cx={cx} cy={cx} r={r} fill="none" stroke={bandFill(s.band)} strokeWidth={stroke}
              strokeLinecap="butt" strokeDasharray={`${dash} ${c - dash}`} strokeDashoffset={-off} transform={`rotate(-90 ${cx} ${cx})`}
              onMouseEnter={(e) => show(e.currentTarget, content)} onMouseLeave={hide} onFocus={(e) => show(e.currentTarget, content)} onBlur={hide}
              aria-label={`${s.name}: ${s.value} standards`}>
              <title>{`${s.name}: ${s.value} (${Math.round(frac * 100)}%)`}</title>
            </circle>
          );
        })}
        <text x={cx} y={cx - 3} textAnchor="middle" dominantBaseline="central" style={{ fontSize: size * 0.26, fontWeight: 700, fill: BRAND.navy }}>{centerValue}</text>
        {centerLabel && (
          <text x={cx} y={cx + size * 0.15} textAnchor="middle" style={{ fontSize: size * 0.082, fill: BRAND.muted, letterSpacing: 0.5, textTransform: 'uppercase' }}>{centerLabel}</text>
        )}
      </svg>
      <Tip tip={tip} />
    </div>
  );
}

/* ───────────────────────── heatmap cell (interactive) ──────────────────── */

export function HeatCell({
  code,
  description,
  pct,
  band,
  nQuestions,
}: {
  code: string;
  description?: string | null;
  pct: number | null;
  band: PerfBandName;
  nQuestions: number;
}) {
  const { ref, tip, show, hide } = useTip();
  const content = (
    <div className="max-w-[220px] whitespace-normal">
      <div className="font-semibold" style={{ color: BRAND.navy }}>{code}</div>
      {description && <div className="my-0.5" style={{ color: BRAND.muted }}>{description}</div>}
      <div className="flex justify-between gap-3">
        <span style={{ color: BRAND.muted }}>Score</span>
        <span className="font-medium tabular-nums" style={{ color: bandFill(band) }}>{pctStr(pct)}</span>
      </div>
      <div className="flex justify-between gap-3">
        <span style={{ color: BRAND.muted }}>Questions</span>
        <span className="font-medium tabular-nums">{nQuestions}</span>
      </div>
    </div>
  );
  const t = bandTone(band);
  return (
    <span ref={ref} className="relative inline-flex">
      <span {...focusable} className="inline-flex min-w-[42px] items-center justify-center rounded px-1 py-1 text-[10.5px] font-semibold tabular-nums transition-transform hover:scale-105"
        style={{ background: t.bg, color: t.fg, border: `1px solid ${t.accent}` }}
        onMouseEnter={(e) => show(e.currentTarget, content)} onMouseLeave={hide}
        onFocus={(e) => show(e.currentTarget, content)} onBlur={hide}
        aria-label={`${code}: ${pctStr(pct)}, ${nQuestions} questions`}>
        {pct === null ? '—' : Math.round(pct)}
      </span>
      <Tip tip={tip} />
    </span>
  );
}
