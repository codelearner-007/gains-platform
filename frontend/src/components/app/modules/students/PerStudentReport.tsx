'use client';

import { useMemo, useState } from 'react';
import { ChevronRight, ExternalLink, GraduationCap } from 'lucide-react';
import type {
  PerfBandName,
  PerStudentReportPayload,
  StudentStandardRow,
  StudentSubjectReport,
} from '@/lib/reports/types';
import { GRID_LINE } from '@/lib/reports/colors';
import ReportPageHeader from '@/components/app/modules/reports/shared/ReportPageHeader';
import { BRAND, bandLabel, bandTone, fmtPct, standardHref } from './bands';
import {
  BulletBar,
  Donut,
  HeatCell,
  Radar,
  ScoreRing,
  TrendLine,
  type RadarAxis,
} from './charts';

/* ─────────────────────────── editorial primitives ──────────────────────── */

/** A section = elegant white card with a brass-accented serif header. */
function Section({
  title,
  subtitle,
  right,
  children,
}: {
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="break-inside-avoid overflow-hidden rounded-xl border bg-white shadow-sm" style={{ borderColor: BRAND.hair }}>
      <header className="flex items-center gap-2.5 border-b px-4 py-2.5" style={{ borderColor: BRAND.hairSoft }}>
        <span className="h-4 w-1 rounded-full" style={{ background: BRAND.brassBright }} aria-hidden />
        <h3 className="font-serif text-[16px] font-semibold tracking-tight" style={{ color: BRAND.navy }}>{title}</h3>
        {subtitle && <span className="text-[11px]" style={{ color: BRAND.faint }}>{subtitle}</span>}
        {right && <div className="ml-auto">{right}</div>}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

/** Section title used above a group of cards (e.g. Subject Detail). */
function GroupTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2.5 break-after-avoid px-1 pt-1">
      <span className="h-4 w-1 rounded-full" style={{ background: BRAND.brassBright }} aria-hidden />
      <h2 className="font-serif text-[17px] font-semibold tracking-tight" style={{ color: BRAND.navy }}>{children}</h2>
    </div>
  );
}

function StatCard({ label, value, sub, accent }: { label: string; value: React.ReactNode; sub?: string; accent?: string }) {
  return (
    <div className="rounded-xl border bg-white px-4 py-3 shadow-sm" style={{ borderColor: BRAND.hair, borderTop: accent ? `3px solid ${accent}` : `1px solid ${BRAND.hair}` }}>
      <div className="text-[10.5px] font-semibold uppercase tracking-wider" style={{ color: BRAND.faint }}>{label}</div>
      <div className="mt-1 font-serif text-[26px] font-bold leading-none tabular-nums" style={{ color: BRAND.navy }}>{value}</div>
      {sub && <div className="mt-1 text-[11px]" style={{ color: BRAND.muted }}>{sub}</div>}
    </div>
  );
}

function BandChip({ pct, band, size = 'md' }: { pct: number | null; band: PerfBandName; size?: 'sm' | 'md' }) {
  const t = bandTone(band);
  return (
    <span className="inline-flex items-center rounded-full font-semibold tabular-nums"
      style={{ background: t.bg, color: t.fg, border: `1px solid ${t.accent}`, padding: size === 'sm' ? '1px 7px' : '2px 10px', fontSize: size === 'sm' ? 11 : 13 }}>
      {fmtPct(pct, size === 'sm' ? 0 : 1)}
    </span>
  );
}

function SubLabel({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-1.5 flex items-center justify-between">
      <span className="text-[10.5px] font-semibold uppercase tracking-wider" style={{ color: BRAND.faint }}>{children}</span>
      {right}
    </div>
  );
}

function Legend({ items }: { items: { swatch: React.ReactNode; label: string }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]" style={{ color: BRAND.muted }}>
      {items.map((it) => (<span key={it.label} className="inline-flex items-center gap-1.5">{it.swatch}{it.label}</span>))}
    </div>
  );
}

function gradeShort(grade?: string | null): string {
  return (grade ?? '').replace(/grade\s*/i, '').trim();
}

/* ─────────────────────────────── overview ──────────────────────────────── */

function OverviewDivider() {
  return <div className="overview-divider hidden self-stretch border-l md:block" style={{ borderColor: BRAND.hairSoft }} aria-hidden />;
}

function MasteryRow({ band, n, total }: { band: PerfBandName; n: number; total: number }) {
  return (
    <div className="flex items-center justify-between gap-2 text-[12px]">
      <span className="inline-flex items-center gap-1.5" style={{ color: BRAND.ink }}>
        <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: bandTone(band).accent }} />
        {bandLabel(band)}
      </span>
      <span className="tabular-nums font-medium" style={{ color: BRAND.ink }}>
        {n}<span style={{ color: BRAND.faint }}> · {total ? Math.round((n / total) * 100) : 0}%</span>
      </span>
    </div>
  );
}

function Overview({ data, subjectLabel }: { data: PerStudentReportPayload; subjectLabel: (s: StudentSubjectReport) => string }) {
  const o = data.overall;
  const axes: RadarAxis[] = data.subjects.map((s) => ({ label: subjectLabel(s), value: s.pct, classValue: s.class_pct }));
  const delta = o.pct !== null && o.class_pct != null ? o.pct - o.class_pct : null;
  const m = o.mastery;
  return (
    <Section title="Performance Overview">
      <div className="overview-grid grid grid-cols-1 items-center gap-6 md:grid-cols-[1fr_auto_1.4fr_auto_1fr]">
        {/* overall ring */}
        <div className="flex flex-col items-center gap-2">
          <ScoreRing pct={o.pct} band={o.band} classPct={o.class_pct} size={132} />
          <span className="rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
            style={{ background: bandTone(o.band).bg, color: bandTone(o.band).fg, border: `1px solid ${bandTone(o.band).accent}` }}>
            {bandLabel(o.band)}
          </span>
          {delta != null && <span className="text-[11px]" style={{ color: BRAND.muted }}>{delta >= 0 ? '+' : ''}{delta.toFixed(1)} pts vs class</span>}
        </div>
        <OverviewDivider />
        {/* cross-subject comparison — radar for 3+ subjects; a per-subject ring
            (student % + vs-class) for 1–2, so the panel always shows a real
            visual instead of a placeholder message. */}
        <div className="flex flex-col items-center gap-2">
          {axes.length >= 3 ? (
            <>
              <Radar axes={axes} size={230} />
              <Legend items={[
                { swatch: <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: `${BRAND.navySoft}44`, border: `1.5px solid ${BRAND.navy}` }} />, label: data.student.first || 'Student' },
                { swatch: <span className="inline-block h-0 w-4" style={{ borderTop: `2px dashed ${BRAND.brassBright}` }} />, label: 'Class average' },
              ]} />
            </>
          ) : (
            <div className="flex min-h-[190px] flex-wrap items-center justify-center gap-x-6 gap-y-3">
              {data.subjects.map((s) => {
                const d = s.pct != null && s.class_pct != null ? s.pct - s.class_pct : null;
                return (
                  <div key={s.subject} className="flex flex-col items-center gap-1">
                    <ScoreRing pct={s.pct} band={s.band} classPct={s.class_pct} size={100} label={subjectLabel(s)} />
                    <span className="text-[11px]" style={{ color: BRAND.muted }}>
                      {d != null ? `${d >= 0 ? '+' : ''}${d.toFixed(1)} pts vs class` : 'class avg n/a'}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
        <OverviewDivider />
        {/* mastery donut */}
        <div className="flex flex-col items-center gap-2">
          <Donut
            segments={[
              { value: m.green, band: 'green', name: bandLabel('green') },
              { value: m.yellow, band: 'yellow', name: bandLabel('yellow') },
              { value: m.pink, band: 'pink', name: bandLabel('pink') },
            ]}
            centerValue={m.total}
            centerLabel="Standards"
            size={132}
          />
          <div className="flex w-full max-w-[200px] flex-col gap-1">
            <MasteryRow band="green" n={m.green} total={m.total} />
            <MasteryRow band="yellow" n={m.yellow} total={m.total} />
            <MasteryRow band="pink" n={m.pink} total={m.total} />
          </div>
        </div>
      </div>
    </Section>
  );
}

/* ─────────────────────── performance by subject ────────────────────────── */

function SubjectBullets({ subjects, subjectLabel }: { subjects: StudentSubjectReport[]; subjectLabel: (s: StudentSubjectReport) => string }) {
  return (
    <Section
      title="Performance by Subject"
      right={
        <Legend items={[
          { swatch: <span className="inline-block h-2.5 w-4 rounded-sm" style={{ background: bandTone('green').accent }} />, label: 'Student' },
          { swatch: <span className="inline-block h-3 w-0.5" style={{ background: BRAND.navy }} />, label: 'Class avg' },
          { swatch: <span className="inline-block h-3 w-0" style={{ borderLeft: `1.5px dashed ${BRAND.brass}` }} />, label: '80% target' },
        ]} />
      }
    >
      <div className="subject-grid grid grid-cols-1 gap-x-10 gap-y-3 md:grid-cols-2">
        {subjects.map((s) => (
          <div key={`${s.subject}-${s.grade}`} className="flex flex-col gap-1">
            <div className="flex items-baseline justify-between">
              <span className="truncate text-[13px] font-medium" style={{ color: BRAND.ink }} title={subjectLabel(s)}>{subjectLabel(s)}</span>
              <span className="text-[13px] font-semibold tabular-nums" style={{ color: bandTone(s.band).fg }}>{fmtPct(s.pct, 0)}</span>
            </div>
            <BulletBar value={s.pct} classValue={s.class_pct} band={s.band} label={subjectLabel(s)} height={16} />
            <span className="text-[10.5px]" style={{ color: BRAND.faint }}>class average {fmtPct(s.class_pct, 0)}</span>
          </div>
        ))}
      </div>
    </Section>
  );
}

/* ─────────────────────────── standards heatmap ─────────────────────────── */

function StandardHeatmap({ standards }: { standards: StudentStandardRow[] }) {
  const byStrand = useMemo(() => {
    const map = new Map<string, StudentStandardRow[]>();
    for (const st of standards) {
      const k = st.strand || 'General';
      if (!map.has(k)) map.set(k, []);
      map.get(k)!.push(st);
    }
    return [...map.entries()];
  }, [standards]);
  return (
    <div className="flex flex-col gap-1.5">
      {byStrand.map(([strand, cells]) => (
        <div key={strand} className="grid grid-cols-[100px_1fr] items-start gap-2">
          <span className="pt-1 text-[10.5px] font-medium leading-tight" style={{ color: BRAND.muted }} title={strand}>{strand}</span>
          <div className="flex flex-wrap gap-1">
            {cells.map((st) => (
              <HeatCell key={st.identifier} code={st.code} description={st.description} pct={st.pct} band={st.band} nQuestions={st.n_questions} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ─────────────────────────────── subject card ──────────────────────────── */

const thStyle: React.CSSProperties = { color: BRAND.muted, fontWeight: 600, fontSize: 11, padding: '5px 8px', textAlign: 'left', borderBottom: `1px solid ${BRAND.hair}`, textTransform: 'uppercase', letterSpacing: '0.03em' };
const tdStyle: React.CSSProperties = { borderBottom: `1px solid ${GRID_LINE}`, padding: '5px 8px', fontSize: 12.5, color: BRAND.ink };

function SubjectCard({ s, label }: { s: StudentSubjectReport; label: string }) {
  const [openTable, setOpenTable] = useState(false);
  const trend = s.assessments.map((a) => ({ label: a.name, date: a.date, value: a.pct, classValue: a.class_pct }));
  return (
    <section className="overflow-hidden rounded-xl border bg-white shadow-sm" style={{ borderColor: BRAND.hair }}>
      <header className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2.5 break-after-avoid" style={{ borderColor: BRAND.hairSoft, background: BRAND.hairSoft }}>
        <div className="flex items-baseline gap-2">
          <span className="h-3.5 w-1 rounded-full" style={{ background: bandTone(s.band).accent }} aria-hidden />
          <h4 className="font-serif text-[15.5px] font-semibold" style={{ color: BRAND.navy }}>{label}</h4>
          {s.assessment_types && <span className="text-[11px]" style={{ color: BRAND.faint }}>· {s.assessment_types}</span>}
        </div>
        <div className="flex items-center gap-2 text-[11px]" style={{ color: BRAND.muted }}>
          <span>class {fmtPct(s.class_pct, 1)}</span>
          <BandChip pct={s.pct} band={s.band} />
        </div>
      </header>

      <div className="subject-split grid grid-cols-1 md:grid-cols-2">
        <div className="border-b p-4 md:border-b-0 md:border-r" style={{ borderColor: GRID_LINE }}>
          <SubLabel>Score Trend</SubLabel>
          {trend.length > 0 ? <TrendLine points={trend} /> : <p className="py-6 text-center text-[12px]" style={{ color: BRAND.muted }}>No assessments in scope.</p>}
        </div>
        <div className="border-b p-4" style={{ borderColor: GRID_LINE }}>
          <SubLabel>Performance by Strand</SubLabel>
          {s.strands.length === 0 ? (
            <p className="py-6 text-center text-[12px]" style={{ color: BRAND.muted }}>No strand alignment for these assessments.</p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {s.strands.map((st) => (
                <div key={st.strand} className="grid grid-cols-[1fr_88px_38px] items-center gap-2">
                  <span className="truncate text-[11.5px]" style={{ color: BRAND.ink }} title={st.strand}>{st.strand}</span>
                  <BulletBar value={st.pct} classValue={null} band={st.band} label={st.strand} height={12} />
                  <span className="text-right text-[11.5px] font-semibold tabular-nums" style={{ color: bandTone(st.band).fg }}>{fmtPct(st.pct, 0)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {s.standards.length > 0 && (
        <div className="border-b p-4" style={{ borderColor: GRID_LINE }}>
          <SubLabel right={
            <button onClick={() => setOpenTable((v) => !v)} className="inline-flex items-center gap-0.5 text-[11px] font-medium transition-colors print:hidden" style={{ color: BRAND.brass }}>
              {openTable ? 'Hide' : 'Show'} standard detail
              <ChevronRight className={`h-3 w-3 transition-transform ${openTable ? 'rotate-90' : ''}`} />
            </button>
          }>Standards Mastery · {s.standards.length} standards</SubLabel>
          <StandardHeatmap standards={s.standards} />
          {openTable && (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full border-collapse">
                <thead><tr>
                  <th style={thStyle}>Standard</th><th style={thStyle}>Description</th>
                  <th style={{ ...thStyle, textAlign: 'center' }}>Q</th><th style={{ ...thStyle, textAlign: 'right' }}>Score</th>
                </tr></thead>
                <tbody>
                  {s.standards.map((st) => {
                    const href = standardHref(st.direct_link);
                    return (
                    <tr key={st.identifier}>
                      <td style={{ ...tdStyle, fontWeight: 600, color: BRAND.navy, whiteSpace: 'nowrap' }}>
                        {href ? (
                          <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 hover:underline">
                            {st.code}<ExternalLink className="h-2.5 w-2.5 print:hidden" style={{ color: BRAND.brass }} />
                          </a>
                        ) : st.code}
                      </td>
                      <td style={tdStyle}>{st.description}</td>
                      <td style={{ ...tdStyle, textAlign: 'center', color: BRAND.muted }}>{st.n_questions}</td>
                      <td style={{ ...tdStyle, textAlign: 'right' }}><BandChip pct={st.pct} band={st.band} size="sm" /></td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {s.assessments.length > 0 && (
        <div className="p-4">
          <SubLabel>Assessment History</SubLabel>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead><tr>
                <th style={thStyle}>Assessment</th><th style={thStyle}>Date</th>
                <th style={{ ...thStyle, textAlign: 'center' }}>Q</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Class</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Score</th>
              </tr></thead>
              <tbody>
                {s.assessments.map((a) => (
                  <tr key={a.item_id}>
                    <td style={{ ...tdStyle, fontWeight: 500 }}>{a.name}</td>
                    <td style={{ ...tdStyle, whiteSpace: 'nowrap', color: BRAND.muted }}>{a.date ?? '—'}</td>
                    <td style={{ ...tdStyle, textAlign: 'center', color: BRAND.muted }}>{a.n_questions}</td>
                    <td style={{ ...tdStyle, textAlign: 'right', color: BRAND.muted }}>{fmtPct(a.class_pct, 0)}</td>
                    <td style={{ ...tdStyle, textAlign: 'right' }}><BandChip pct={a.pct} band={a.band} size="sm" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

/* ─────────────────────────────── main report ───────────────────────────── */

export default function PerStudentReport({ data }: { data: PerStudentReportPayload }) {
  const subjectLabel = useMemo(() => {
    const counts = new Map<string, number>();
    for (const s of data.subjects) counts.set(s.subject, (counts.get(s.subject) ?? 0) + 1);
    return (s: StudentSubjectReport) =>
      (counts.get(s.subject) ?? 0) > 1 && s.grade ? `${s.subject} (${gradeShort(s.grade)})` : s.subject;
  }, [data.subjects]);

  const idLine = [
    data.grades.length ? `Grade ${data.grades.map(gradeShort).join(', ')}` : null,
    data.student.grad_year ? `Class of ${data.student.grad_year}` : null,
    `ID ${data.student.uid}`,
  ].filter(Boolean).join('  ·  ');

  const header = (
    <ReportPageHeader
      logoUrl={data.school.logo_url}
      schoolName={data.school.name || undefined}
      title={data.student.name}
      caption="Student Performance Report"
      subtitle={idLine}
      meta={`Academic Year ${data.session || data.school.current_session || '—'}`}
    />
  );

  const shell = (children: React.ReactNode) => (
    <div className="per-student-report flex flex-col gap-3 rounded-lg bg-[#F7F5EF] p-3 print:!bg-white print:!gap-2 print:!p-0">
      {children}
    </div>
  );

  if (!data.has_data || data.subjects.length === 0) {
    return shell(
      <>
        {header}
        <div className="rounded-xl border bg-white p-10 text-center shadow-sm" style={{ borderColor: BRAND.hair }}>
          <GraduationCap className="mx-auto mb-3 h-8 w-8" style={{ color: BRAND.faint }} />
          <p className="text-[15px] font-semibold" style={{ color: BRAND.navy }}>No scored data</p>
          <p className="mt-1 text-sm" style={{ color: BRAND.muted }}>This student has no scored assessment data for {data.session || 'the selected year'}.</p>
        </div>
      </>,
    );
  }

  const o = data.overall;
  const kpis = [
    { label: 'Overall %', value: fmtPct(o.pct, 1), sub: `class ${fmtPct(o.class_pct, 1)}`, accent: bandTone(o.band).accent },
    { label: 'Class Average', value: fmtPct(o.class_pct, 1) },
    { label: 'Subjects', value: o.n_subjects },
    { label: 'Assessments', value: o.n_assessments },
    { label: 'Standards', value: o.n_standards },
  ];

  return shell(
    <>
      {header}
      <div className="kpi-grid grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {kpis.map((k) => (<StatCard key={k.label} label={k.label} value={k.value} sub={k.sub} accent={k.accent} />))}
      </div>

      <Overview data={data} subjectLabel={subjectLabel} />
      <SubjectBullets subjects={data.subjects} subjectLabel={subjectLabel} />

      <GroupTitle>Subject Detail</GroupTitle>
      {data.subjects.map((s) => (
        <SubjectCard key={`${s.subject}-${s.grade}`} s={s} label={subjectLabel(s)} />
      ))}

      <footer className="flex flex-wrap items-center justify-between gap-2 px-1 pt-1 text-[10.5px] print:hidden" style={{ color: BRAND.faint }}>
        <span>Confidential student performance report · latest attempt</span>
        <span>Bands: ≥80 at target · 70–80 approaching · &lt;70 needs attention</span>
      </footer>
    </>,
  );
}
