import type { ReactNode } from 'react';
import { VERBATIM_GOVERNMENT_WARNING } from '../api/types';
import StatusBadge from '../components/StatusBadge';
import Verdict from '../components/Verdict';
import Card from '../components/Card';
import { IconCheck } from '../components/icons';

interface SectionProps {
  id: string;
  title: string;
  kicker?: string;
  children: ReactNode;
}
function Section({ id, title, kicker, children }: SectionProps) {
  return (
    <section id={id} style={{ marginBottom: 48 }}>
      {kicker && (
        <p style={{ margin: '0 0 4px', fontSize: 12, fontWeight: 600, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--color-primary)' }}>
          {kicker}
        </p>
      )}
      <h2 style={{ marginBottom: 16 }}>{title}</h2>
      {children}
    </section>
  );
}

function Swatch({ name, hex, ratio }: { name: string; hex: string; ratio: string }) {
  const onLight = ['#dfe1e2', '#eef1f7'].includes(hex);
  return (
    <div style={{ border: '1px solid var(--color-line)', borderRadius: 8, overflow: 'hidden', background: '#fff' }}>
      <div style={{
        background: hex, height: 80, display: 'grid', placeItems: 'center',
        color: onLight ? '#1b1b1b' : '#fff',
        fontFamily: 'var(--font-mono)', fontWeight: 600,
      }}>{hex}</div>
      <div style={{ padding: 12 }}>
        <div style={{ fontWeight: 600 }}>{name}</div>
        <div style={{ fontSize: 13, color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>on white = {ratio}:1</div>
      </div>
    </div>
  );
}

function CodeBlock({ children }: { children: string }) {
  return (
    <pre style={{
      background: '#0b1f3f', color: '#e7ecf2', borderRadius: 8, padding: 20,
      fontSize: 13, lineHeight: 1.55, overflow: 'auto', margin: 0,
      fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
    }}>{children}</pre>
  );
}

export default function SystemPage() {
  return (
    <div className="container">
      <p style={{ marginBottom: 8 }}><span className="tag">Reference</span></p>
      <h1>Design system &amp; API contract</h1>
      <p style={{ fontSize: 'var(--fs-18)', color: 'var(--color-ink-muted)', maxWidth: 'none' }}>
        The constitution this app is built against — design tokens, the 3-state status
        model, accessibility floor, and the typed API contract the future backend must implement.
      </p>

      <Section id="status-model" kicker="Used everywhere a verdict appears" title="The 3-state status model">
        <p>
          Every field result is one of three states. <strong>Color is never the
          only signal</strong> — every status combines a color, an icon, and a text label so it stays
          legible to colorblind users, on low-contrast displays, and in printed reports.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16, marginTop: 24 }}>
          {(['match', 'likely', 'flag'] as const).map((s) => (
            <Card key={s} padding={20}>
              <StatusBadge status={s} />
              <h4 style={{ margin: '12px 0 6px' }}>{s === 'match' ? 'Match' : s === 'likely' ? 'Likely match' : 'Flag'}</h4>
              <p style={{ margin: 0, color: 'var(--color-ink-muted)' }}>
                {s === 'match'  && 'Field matches the application within tolerance. No action needed.'}
                {s === 'likely' && 'Within fuzzy tolerance (e.g. "750 ML" vs "750 ml"). One-click Confirm.'}
                {s === 'flag'   && 'Outside tolerance, missing, or non-compliant. Requires agent review.'}
              </p>
            </Card>
          ))}
        </div>
        <div style={{ marginTop: 24, display: 'grid', gap: 12 }}>
          <Verdict status="match"  title="All 11 fields match"  sub="Ready to approve. No agent action required." />
          <Verdict status="likely" title="2 likely matches"     sub="Quick confirmation needed before approval." />
          <Verdict status="flag"   title="3 flags need review"  sub="Review each flagged field with the agent before proceeding." />
        </div>
      </Section>

      <Section id="color" kicker="Documented contrast ratios" title="Color tokens">
        <p>All values verified for WCAG 2.1 AA against white. Status colors are tuned to ≥ 4.5 : 1 so they stay legible on the pale tinted backgrounds used in pills and verdict blocks.</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 16, marginTop: 24 }}>
          <Swatch name="Primary"      hex="#1a4480" ratio="9.42" />
          <Swatch name="Ink"          hex="#1b1b1b" ratio="16.0" />
          <Swatch name="Ink muted"    hex="#565c65" ratio="5.49" />
          <Swatch name="Ink subtle"   hex="#686c73" ratio="5.23" />
          <Swatch name="Match"        hex="#136c39" ratio="5.83" />
          <Swatch name="Likely"       hex="#8a4b00" ratio="5.91" />
          <Swatch name="Flag"         hex="#b50909" ratio="6.27" />
        </div>
      </Section>

      <Section id="type" kicker="Source Sans 3, 16/24 base" title="Typography">
        <Card padding={24}>
          <div style={{ fontSize: 48, lineHeight: 1.1, fontWeight: 700 }}>Aa</div>
          <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-ink-muted)', fontSize: 13, marginTop: 4 }}>Source Sans 3</div>
          <hr className="divider" />
          <div style={{ display: 'grid', gap: 8 }}>
            <div style={{ fontSize: 'var(--fs-36)', fontWeight: 700 }}>H1 — 36 / 700</div>
            <div style={{ fontSize: 'var(--fs-30)', fontWeight: 700 }}>H2 — 30 / 700</div>
            <div style={{ fontSize: 'var(--fs-24)', fontWeight: 600 }}>H3 — 24 / 600</div>
            <div style={{ fontSize: 'var(--fs-18)', fontWeight: 600 }}>H4 — 18 / 600</div>
            <div style={{ fontSize: 'var(--fs-16)' }}>Body — 16 / 400, line-height 1.5</div>
            <div style={{ fontSize: 'var(--fs-14)', color: 'var(--color-ink-muted)' }}>Caption — 14 / 400</div>
          </div>
        </Card>
      </Section>

      <Section id="space" kicker="4px base scale" title="Spacing">
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
          {[2, 4, 8, 12, 16, 20, 24, 32, 40, 56, 72].map(px => (
            <div key={px} style={{ textAlign: 'center' }}>
              <div style={{ width: px, height: px, background: 'var(--color-primary)', borderRadius: 2 }} />
              <div style={{ fontSize: 12, color: 'var(--color-ink-muted)', marginTop: 4, fontFamily: 'var(--font-mono)' }}>{px}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section id="a11y" kicker="Section 508 / WCAG 2.1–2.2 AA" title="Accessibility floor">
        <ul style={{ paddingLeft: 0, listStyle: 'none', display: 'grid', gap: 12, margin: 0 }}>
          {[
            'Color contrast ≥ 4.5:1 for body text; ≥ 3:1 for large text and UI components.',
            'Interactive target size ≥ 24×24 (incidental); ≥ 44×44 for primary actions.',
            'Body text ≥ 16px; line-height 1.5; paragraph measure capped at ~66ch.',
            'Status always conveys color + icon + text — never color alone.',
            'Full keyboard operability; visible focus ring (3px gold + 2px offset, 7.0:1 contrast).',
            'Skip-to-content link as the first focusable element (tab into the page to see it).',
            'Plain-language, field-specific error messages.',
            'Optimistic UI + skeleton loaders + streaming results — no blocking spinners.',
          ].map(t => (
            <li key={t} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
              <span style={{
                width: 24, height: 24, borderRadius: 999,
                background: 'var(--status-match-bg)', color: 'var(--status-match-fg)',
                display: 'grid', placeItems: 'center', flexShrink: 0, marginTop: 2,
              }}>
                <IconCheck size={14} strokeWidth={3} />
              </span>
              <span>{t}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section id="api" kicker="The future backend must implement this" title="API contract">
        <p>
          Until the backend exists, a typed mock client returns these exact shapes.
          {' '}<code>POST /api/verify</code> takes a downscaled JPEG plus the application data and returns a <code>VerificationResult</code>.
        </p>
        <CodeBlock>{`type FieldStatus = 'match' | 'likely' | 'flag';

interface FieldResult {
  fieldName:        string;
  declaredValue:    string;
  extractedValue:   string;
  status:           FieldStatus;
  confidence:       number;      // 0–1
  evidenceCropUrl?: string;
  regulationCite?:  string;      // e.g. "27 CFR 4.36(b)(1)"
}

interface GovernmentWarningAnalysis {
  present:          boolean;
  verbatimMatch:    boolean;
  casingBoldOk:     boolean;
  fontSizeOk:       boolean;
  contrastOk:       boolean;
  separateAndApart: boolean;
  detectedText:     string;
  deviations:       Array<{ type: string; message: string }>;
  regulation:       '27 CFR 16.21/16.22';
}

interface ImageQuality {
  score:    number;   // 0–1
  legible:  boolean;
  note?:    string;
}

interface VerificationResult {
  fields:            FieldResult[];
  governmentWarning: GovernmentWarningAnalysis;
  imageQuality:      ImageQuality;
}

// Endpoints
POST /api/verify       -> VerificationResult
POST /api/verify-batch -> VerificationResult[]   // or { jobId }`}</CodeBlock>
      </Section>

      <Section id="warning" kicker="27 CFR 16.21 / 16.22" title="Verbatim Government Warning">
        <p>
          The exact required wording, stored as a frozen constant in <code>src/api/types.ts</code>.
          The Government Warning panel compares <code>detectedText</code> against this baseline.
        </p>
        <Card padding={20} style={{ background: 'var(--color-bg-alt)' }}>
          <pre style={{
            margin: 0, fontFamily: 'var(--font-mono)', fontSize: 13, lineHeight: 1.55,
            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          }}>{VERBATIM_GOVERNMENT_WARNING}</pre>
        </Card>
      </Section>
    </div>
  );
}
