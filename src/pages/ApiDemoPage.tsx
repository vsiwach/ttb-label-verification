import { useRef, useState } from 'react';
import type { VerificationField, VerificationResult } from '../api/types';
import { groupFor } from '../api/types';
import { verifyLabel } from '../api/client';
import { SCENARIOS } from '../api/mockData';
import { requiredFields } from '../api/ttbRules';
import type { BeverageType } from '../api/ttbRules';
import Alert from '../components/Alert';
import Button from '../components/Button';
import Card from '../components/Card';
import StatusBadge from '../components/StatusBadge';
import { IconClock, IconPlay } from '../components/icons';

type ScenarioKey = 'A' | 'B' | 'C';

interface LogEntry {
  t: number;
  text: string;
  color?: string;
}

interface ScenarioSummary {
  fieldsByStatus: Record<'match' | 'likely' | 'flag', number>;
  gwOk: boolean;
  imgScore: number;
  elapsed: number;
}

export default function ApiDemoPage() {
  const [running, setRunning]     = useState<ScenarioKey | null>(null);
  const [log, setLog]             = useState<LogEntry[]>([]);
  const [summaries, setSummaries] = useState<Partial<Record<ScenarioKey, ScenarioSummary>>>({});
  const startedAt = useRef(0);

  function append(text: string, color?: string) {
    const t = (performance.now() - startedAt.current) / 1000;
    setLog(prev => [...prev, { t, text, color }]);
    // eslint-disable-next-line no-console
    console.log(`[verify] t+${t.toFixed(2)}s  ${text}`);
  }

  async function runScenario(key: ScenarioKey) {
    setLog([]);
    setRunning(key);
    startedAt.current = performance.now();
    const scenario = SCENARIOS[key];
    append(`▶ verifyLabel  scenario=${key}  brand="${scenario.applicationData.brandName}"`, '#9ad4ff');

    const fieldsByStatus: Record<'match' | 'likely' | 'flag', number> = { match: 0, likely: 0, flag: 0 };

    const result: VerificationResult = await verifyLabel(
      null,
      scenario.applicationData,
      (field: VerificationField, i: number, total: number) => {
        fieldsByStatus[field.status]++;
        const color = field.status === 'match' ? '#7fd99a'
                    : field.status === 'likely' ? '#ffd97a'
                    : '#ff9a8a';
        append(
          `  ↳ field ${i + 1}/${total}  ${field.fieldName.padEnd(22)} ${field.status.toUpperCase()}  (conf ${field.confidence.toFixed(2)})  "${field.extractedValue}"`,
          color,
        );
      },
      {
        onGovernmentWarning: (gw) => {
          const ok = gw.verbatimMatch && gw.casingBoldOk && gw.fontSizeOk;
          append(
            `  ↳ governmentWarning  verbatim=${gw.verbatimMatch}  casingBold=${gw.casingBoldOk}  fontSize=${gw.fontSizeOk}  deviations=${gw.deviations.length}`,
            ok ? '#7fd99a' : '#ff9a8a',
          );
        },
        onImageQuality: (iq) => {
          append(`  ↳ imageQuality  score=${iq.score.toFixed(2)}  legible=${iq.legible}`, '#9ad4ff');
        },
      },
    );

    const elapsed = (performance.now() - startedAt.current) / 1000;
    append(`✓ done in ${elapsed.toFixed(2)}s  group="${groupFor(result)}"`, '#9ad4ff');

    setSummaries(prev => ({
      ...prev,
      [key]: {
        fieldsByStatus,
        gwOk: result.governmentWarning.verbatimMatch && result.governmentWarning.casingBoldOk,
        imgScore: result.imageQuality.score,
        elapsed,
      },
    }));
    setRunning(null);
  }

  return (
    <div className="container">
      <p style={{ marginBottom: 8 }}><span className="tag">Acceptance check</span></p>
      <h1>Mock API — streaming demo</h1>
      <p style={{ fontSize: 'var(--fs-18)', color: 'var(--color-ink-muted)', maxWidth: 'none', marginBottom: 32 }}>
        Press <strong>Run</strong> on any scenario. <code>verifyLabel()</code> emits each
        field over ~2–4&nbsp;seconds, then the government warning and image quality at the
        end. The live log below mirrors the same stream to your browser console for the acceptance check.
      </p>

      <Alert variant="info" title="What this proves">
        The API contract is the single source of truth. With <code>VITE_API_BASE_URL</code> empty,
        the client serves fixtures from <code>src/api/mockData.ts</code>; set the env var to the
        real backend URL and the same <code>verifyLabel</code> / <code>verifyBatch</code> functions
        hit it instead — no code change.
      </Alert>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16, margin: '32px 0' }}>
        {(['A', 'B', 'C'] as ScenarioKey[]).map(k => (
          <ScenarioCard
            key={k}
            scenarioKey={k}
            onRun={runScenario}
            running={running === k}
            summary={summaries[k]}
          />
        ))}
      </div>

      <Card title="Stream log" titleLevel={3} headerSlot={<Button variant="ghost" onClick={() => setLog([])}>Clear</Button>}>
        <StreamLog entries={log} />
      </Card>

      <div style={{ marginTop: 32, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
        <Card title="Verbatim warning (the baseline)" titleLevel={3}>
          <pre style={{
            background: 'var(--color-bg-alt)', padding: 16, borderRadius: 6,
            fontSize: 13, lineHeight: 1.5, margin: 0, whiteSpace: 'pre-wrap',
            fontFamily: 'var(--font-mono)',
          }}>{
`GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.`
          }</pre>
          <p style={{ margin: '12px 0 0', color: 'var(--color-ink-muted)', fontSize: 14 }}>
            Stored as a frozen constant; this is what the warning analyser compares
            <code> detectedText </code>against.
          </p>
        </Card>
        <Card title="Required fields by beverage type" titleLevel={3}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14, tableLayout: 'fixed' }}>
            <thead>
              <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--color-line)' }}>
                <th style={{ padding: '8px 0', width: '30%' }}>Beverage</th>
                <th style={{ padding: '8px 0' }}>Required fields</th>
              </tr>
            </thead>
            <tbody>
              {(['spirits', 'wine', 'beer', 'malt'] as BeverageType[]).map(bt => (
                <tr key={bt} style={{ borderBottom: '1px solid var(--color-line)' }}>
                  <td style={{ padding: '10px 12px 10px 0', fontWeight: 600, textTransform: 'capitalize' }}>{bt}</td>
                  <td style={{ padding: '10px 0', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-muted)', wordBreak: 'break-word' }}>
                    {requiredFields(bt).join(', ') + ' + governmentWarning'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ margin: '12px 0 0', color: 'var(--color-ink-muted)', fontSize: 14 }}>
            Beer/malt require alcohol content <em>only</em> when added nonbeverage
            flavorings are present. Imports also require country of origin.
          </p>
        </Card>
      </div>
    </div>
  );
}

interface ScenarioCardProps {
  scenarioKey: ScenarioKey;
  onRun: (k: ScenarioKey) => void;
  running: boolean;
  summary?: ScenarioSummary;
}

function ScenarioCard({ scenarioKey, onRun, running, summary }: ScenarioCardProps) {
  const scenario = SCENARIOS[scenarioKey];
  const app = scenario.applicationData;
  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0, flex: '1 1 220px' }}>
          <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--color-primary)' }}>
            Scenario {scenarioKey}
          </div>
          <h3 style={{ margin: '6px 0 4px' }}>{app.brandName}</h3>
          <p style={{ margin: 0, color: 'var(--color-ink-muted)' }}>{scenario.label}</p>
          <p style={{ margin: '8px 0 0', color: 'var(--color-ink-subtle)', fontSize: 14 }}>
            COLA {app.colaNumber} · {app.classType} · {app.netContents}
          </p>
        </div>
        <Button icon={IconPlay} onClick={() => onRun(scenarioKey)} disabled={running}>
          {running ? 'Running…' : 'Run'}
        </Button>
      </div>
      {summary && (
        <>
          <hr className="divider" />
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {summary.fieldsByStatus.match  > 0 && <StatusBadge status="match" />}
            {summary.fieldsByStatus.likely > 0 && <StatusBadge status="likely" />}
            {summary.fieldsByStatus.flag   > 0 && <StatusBadge status="flag" />}
            <span className="tag">
              {summary.fieldsByStatus.match} match · {summary.fieldsByStatus.likely} likely · {summary.fieldsByStatus.flag} flag
            </span>
            <span className="tag">warning {summary.gwOk ? 'verbatim' : 'deviated'}</span>
            <span className="tag">image q {Math.round(summary.imgScore * 100)}%</span>
            <span className="tag">
              <IconClock size={12} /> {summary.elapsed.toFixed(2)}s
            </span>
          </div>
        </>
      )}
    </Card>
  );
}

function StreamLog({ entries }: { entries: LogEntry[] }) {
  return (
    <div
      role="log"
      aria-live="polite"
      aria-relevant="additions"
      style={{
        background: '#0b1f3f', color: '#e7ecf2', borderRadius: 8, padding: 16,
        fontSize: 13, lineHeight: 1.55, maxHeight: 320, overflow: 'auto',
        fontFamily: 'var(--font-mono)',
      }}
    >
      {entries.length === 0 ? (
        <div style={{ color: '#8ca0b8' }}>Stream is idle. Press a scenario button to start.</div>
      ) : entries.map((e, i) => (
        <div key={i} style={{
          display: 'flex', gap: 12, alignItems: 'baseline',
          padding: '2px 0', borderTop: i ? '1px dashed rgba(255,255,255,.08)' : 'none',
        }}>
          <span style={{ color: '#8ca0b8', width: 64, flexShrink: 0 }}>t+{e.t.toFixed(2)}s</span>
          <span style={{ color: e.color || '#e7ecf2' }}>{e.text}</span>
        </div>
      ))}
    </div>
  );
}
