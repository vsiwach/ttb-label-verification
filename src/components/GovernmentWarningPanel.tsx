import { useEffect, useMemo, useState } from 'react';
import type { GovernmentWarningAnalysis } from '../api/types';
import { VERBATIM_GOVERNMENT_WARNING } from '../api/types';
import Alert from './Alert';
import StatusBadge from './StatusBadge';
import { SkeletonLine } from './Skeleton';
import { IconCheck, IconChevronR, IconFlag } from './icons';

// ─────────────────────────────────────────────────────────────────────────────
// Word-level diff (LCS) between detected and required text.
// ─────────────────────────────────────────────────────────────────────────────
type DiffOp =
  | { op: 'equal'; a: string; b: string }
  | { op: 'case'; a: string; b: string }
  | { op: 'del-a'; a: string }
  | { op: 'add-b'; b: string };

function wordDiff(aStr: string, bStr: string): DiffOp[] {
  const aTok = aStr.split(/(\s+)/).filter(Boolean);
  const bTok = bStr.split(/(\s+)/).filter(Boolean);
  const a = aTok.map(t => ({ t, ws: /^\s+$/.test(t) }));
  const b = bTok.map(t => ({ t, ws: /^\s+$/.test(t) }));
  const norm = (s: string) => s.toLowerCase().replace(/[.,!?:;()]/g, '');

  const n = a.length;
  const m = b.length;
  const dp: Int32Array[] = [];
  for (let i = 0; i <= n; i++) dp.push(new Int32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      const matchable =
        (a[i].ws && b[j].ws) ||
        (!a[i].ws && !b[j].ws && norm(a[i].t) === norm(b[j].t));
      dp[i][j] = matchable
        ? 1 + dp[i + 1][j + 1]
        : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  const ops: DiffOp[] = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i].ws && b[j].ws) { ops.push({ op: 'equal', a: a[i].t, b: b[j].t }); i++; j++; continue; }
    if (a[i].ws) { ops.push({ op: 'del-a', a: a[i].t }); i++; continue; }
    if (b[j].ws) { ops.push({ op: 'add-b', b: b[j].t }); j++; continue; }
    if (norm(a[i].t) === norm(b[j].t)) {
      const caseDiff = a[i].t !== b[j].t;
      ops.push({ op: caseDiff ? 'case' : 'equal', a: a[i].t, b: b[j].t });
      i++; j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      ops.push({ op: 'del-a', a: a[i].t });
      i++;
    } else {
      ops.push({ op: 'add-b', b: b[j].t });
      j++;
    }
  }
  while (i < n) { ops.push({ op: 'del-a', a: a[i].t }); i++; }
  while (j < m) { ops.push({ op: 'add-b', b: b[j].t }); j++; }
  return ops;
}

function DetectedText({ ops }: { ops: DiffOp[] }) {
  return (
    <p className="gw-text gw-text--detected">
      {ops.map((o, i) => {
        if (o.op === 'add-b') return null;
        if (o.op === 'equal') return <span key={i}>{o.a}</span>;
        if (o.op === 'case')  return <span key={i} className="gw-mark gw-mark--case" title={`Casing differs from required: should be "${o.b}"`}>{o.a}</span>;
        if (/^\s+$/.test(o.a)) return <span key={i}>{o.a}</span>;
        return <span key={i} className="gw-mark gw-mark--del" title="This word does not appear in the required text">{o.a}</span>;
      })}
    </p>
  );
}

function RequiredText({ ops }: { ops: DiffOp[] }) {
  return (
    <p className="gw-text gw-text--required">
      {ops.map((o, i) => {
        if (o.op === 'del-a') return null;
        if (o.op === 'equal') return <span key={i}>{o.b}</span>;
        if (o.op === 'case')  return <span key={i}>{o.b}</span>;
        if (/^\s+$/.test(o.b)) return <span key={i}>{o.b}</span>;
        return <span key={i} className="gw-mark gw-mark--add" title="Missing from detected text">{o.b}</span>;
      })}
    </p>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Checks
// ─────────────────────────────────────────────────────────────────────────────
const CHECKS: Array<{ key: keyof GovernmentWarningAnalysis; title: string; ok: string; bad: string }> = [
  { key: 'present',          title: 'Statement present',                                ok: 'Found on the label',                  bad: 'Not detected on the label' },
  { key: 'verbatimMatch',    title: 'Exact verbatim wording',                           ok: 'Wording matches the required text',   bad: 'Wording does not match — see diff below' },
  { key: 'casingBoldOk',     title: '"GOVERNMENT WARNING" all caps and bold',           ok: 'Correctly styled',                    bad: 'Title is not ALL CAPS and/or not bold' },
  { key: 'fontSizeOk',       title: 'Minimum type size for container',                  ok: 'Meets the minimum',                   bad: 'Appears below the minimum type size' },
  { key: 'contrastOk',       title: 'Adequate contrast',                                ok: 'Legible against background',          bad: 'Contrast is too low for legibility' },
  { key: 'separateAndApart', title: '"Separate and apart" from other copy',             ok: 'Stands alone on the label',           bad: 'Interspersed with other label copy' },
];

function CheckRow({ ok, title, label }: { ok: boolean; title: string; label: string }) {
  const tone = ok ? 'match' : 'flag';
  const Icon = ok ? IconCheck : IconFlag;
  return (
    <li className="gw-check">
      <span className={`gw-check__dot gw-check__dot--${tone}`} aria-hidden="true">
        <Icon size={14} strokeWidth={3} />
      </span>
      <div className="gw-check__body">
        <div className="gw-check__title">
          {title}
          <span className={`gw-pill gw-pill--${tone}`}>{ok ? 'OK' : 'Does not comply'}</span>
        </div>
        <div className="gw-check__label">{label}</div>
      </div>
    </li>
  );
}

function DiffLegend() {
  return (
    <div className="gw__legend" aria-label="Diff legend">
      <span className="gw__legend-item">
        <span className="gw-mark gw-mark--case" style={{ pointerEvents: 'none' }}>case</span>
        casing differs
      </span>
      <span className="gw__legend-item">
        <span className="gw-mark gw-mark--del" style={{ pointerEvents: 'none' }}>wording</span>
        not in required text
      </span>
      <span className="gw__legend-item">
        <span className="gw-mark gw-mark--add" style={{ pointerEvents: 'none' }}>missing</span>
        missing word (shown when expanded)
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Panel
// ─────────────────────────────────────────────────────────────────────────────
export interface GovernmentWarningPanelProps {
  gw: GovernmentWarningAnalysis | null;
  loading?: boolean;
}

export default function GovernmentWarningPanel({ gw, loading }: GovernmentWarningPanelProps) {
  const [showRequired, setShowRequired] = useState(false);
  const [liveMsg, setLiveMsg] = useState('');

  const status = useMemo(() => {
    if (!gw) return null;
    const failures = CHECKS.filter(c => gw[c.key] === false).length;
    return failures === 0 ? { tone: 'match' as const, failures } : { tone: 'flag' as const, failures };
  }, [gw]);

  useEffect(() => {
    if (!gw || !status) return;
    setLiveMsg(
      status.tone === 'match'
        ? 'Government Warning: compliant. All six checks pass.'
        : `Government Warning: ${status.failures} ${status.failures === 1 ? 'issue' : 'issues'} found. Review required.`,
    );
  }, [gw, status]);

  const ops = useMemo(() => {
    if (!gw?.detectedText) return [];
    return wordDiff(gw.detectedText, VERBATIM_GOVERNMENT_WARNING);
  }, [gw]);

  if (loading || !gw || !status) {
    return (
      <section className="gw" aria-busy="true">
        <header className="gw__header gw__header--loading">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1 }}>
            <span style={{ width: 32, height: 32, borderRadius: 16, background: 'var(--color-bg-alt)', flexShrink: 0 }} aria-hidden="true" />
            <div style={{ flex: 1 }}>
              <SkeletonLine width="40%" height={16} />
              <div style={{ height: 6 }} />
              <SkeletonLine width="60%" height={11} />
            </div>
          </div>
        </header>
        <div className="gw__body">
          <SkeletonLine width="80%" height={10} />
          <div style={{ height: 8 }} />
          <SkeletonLine width="65%" height={10} />
          <div style={{ height: 8 }} />
          <SkeletonLine width="72%" height={10} />
        </div>
      </section>
    );
  }

  const compliant = status.tone === 'match';

  return (
    <section className="gw" aria-labelledby="gw-heading">
      <header className={`gw__header gw__header--${status.tone}`}>
        <span className="gw__verdict-icon" aria-hidden="true">
          {compliant ? <IconCheck size={22} strokeWidth={2.5} /> : <IconFlag size={22} strokeWidth={2.5} />}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p className="gw__kicker">Government Warning · 27 CFR 16.21 / 16.22</p>
          <h3 id="gw-heading" className="gw__title">
            {compliant ? 'Compliant' : `${status.failures} ${status.failures === 1 ? 'issue' : 'issues'} found — review required`}
          </h3>
        </div>
        <StatusBadge status={compliant ? 'match' : 'flag'} />
      </header>

      <p className="sr-only" role="status" aria-live="polite">{liveMsg}</p>

      <div className="gw__body">
        <h4 className="gw__h4">Compliance checks</h4>
        <ul className="gw__checks" aria-label="Government Warning compliance checks">
          {CHECKS.map(c => (
            <CheckRow
              key={c.key as string}
              ok={gw[c.key] === true}
              title={c.title}
              label={gw[c.key] === true ? c.ok : c.bad}
            />
          ))}
        </ul>

        <div className="gw__diff-head">
          <h4 className="gw__h4" style={{ margin: 0 }}>Detected text on the label</h4>
          <button
            type="button"
            className="btn btn--ghost"
            aria-expanded={showRequired}
            aria-controls="gw-required"
            onClick={() => setShowRequired(s => !s)}
          >
            {showRequired ? 'Hide required text' : 'Show required text'}
            <span aria-hidden="true" style={{
              display: 'inline-block', marginLeft: 4,
              transform: showRequired ? 'rotate(90deg)' : 'rotate(0deg)',
              transition: 'transform 160ms',
            }}>
              <IconChevronR size={16} />
            </span>
          </button>
        </div>

        {ops.length > 0 ? (
          <div className={`gw__compare ${showRequired ? 'gw__compare--split' : ''}`}>
            <div className="gw__pane">
              <div className="gw__pane-label">Detected on label</div>
              <DetectedText ops={ops} />
              {!compliant && <DiffLegend />}
            </div>
            {showRequired && (
              <div id="gw-required" className="gw__pane gw__pane--required">
                <div className="gw__pane-label">Required text (27 CFR 16.21 / 16.22)</div>
                <RequiredText ops={ops} />
              </div>
            )}
          </div>
        ) : (
          <Alert variant="error" title="No warning text detected on the label">
            <p>
              The Government Warning statement is required on every alcohol beverage
              label ≥ 0.5% ABV. Confirm with the applicant and request a corrected label.
            </p>
          </Alert>
        )}

        {gw.deviations.length > 0 && (
          <>
            <h4 className="gw__h4">What an agent should action</h4>
            <ul className="gw__deviations">
              {gw.deviations.map((d, i) => (
                <li key={i} className="gw__deviation">
                  <span className="gw__deviation-type">{d.type}</span>
                  <span>{d.message}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      <footer className="gw__foot">
        Per <strong>27 CFR 16.21</strong> and <strong>16.22</strong>
        {' '}— Health Warning Statement requirements for alcohol beverages.
      </footer>
    </section>
  );
}
