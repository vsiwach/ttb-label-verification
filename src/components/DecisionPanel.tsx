import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import type {
  ApplicationData, GovernmentWarningAnalysis, ImageQuality,
  VerificationField, VerificationResult,
} from '../api/types';
import { verifyStore } from '../store/verifyStore';
import Alert from './Alert';
import Button from './Button';
import { IconArrowL, IconArrowR, IconCheck, IconClose, IconImage, IconInfo } from './icons';

// TODO(backend): when the API exists, POST decisions to ${API_BASE_URL}/decisions
// with the entry shape below. Local-storage staging keeps demos working offline.
export const DECISIONS_STORAGE_KEY = 'ttb-decisions';

export type DecisionMode = 'approve' | 'reject' | 'requestImage';

export interface DecisionEntry {
  brand: string;
  colaNumber?: string;
  decision: DecisionMode;
  reasons: string[];
  freeText: string;
  logEntry: string;
  savedAt: string;
  agent: string;
}

export interface SuggestedReason {
  id: string;
  text: string;
  category: 'field' | 'warning';
  severity: 'flag' | 'likely';
  defaultChecked: boolean;
}

export function saveDecisionLocally(entry: DecisionEntry): void {
  try {
    const raw = window.localStorage.getItem(DECISIONS_STORAGE_KEY);
    const prev = raw ? (JSON.parse(raw) as DecisionEntry[]) : [];
    prev.unshift(entry);
    window.localStorage.setItem(DECISIONS_STORAGE_KEY, JSON.stringify(prev.slice(0, 50)));
  } catch (e) {
    console.warn('Decision not persisted:', e);
  }
}

export function deriveReasons(result: VerificationResult): SuggestedReason[] {
  const reasons: SuggestedReason[] = [];
  for (const f of result.fields) {
    if (f.status === 'flag') {
      reasons.push({
        id: `flag:${f.fieldName}`,
        text: `${f.fieldName} mismatch: declared "${f.declaredValue}", label shows "${f.extractedValue}".`,
        category: 'field', severity: 'flag', defaultChecked: true,
      });
    } else if (f.status === 'likely') {
      reasons.push({
        id: `likely:${f.fieldName}`,
        text: `${f.fieldName} differs from the application: "${f.declaredValue}" vs "${f.extractedValue}".`,
        category: 'field', severity: 'likely', defaultChecked: false,
      });
    }
  }
  const gw = result.governmentWarning;
  if (gw) {
    const gwFails: Array<{ key: keyof GovernmentWarningAnalysis; msg: string }> = [
      { key: 'present',          msg: 'Government Warning not detected on the label.' },
      { key: 'verbatimMatch',    msg: 'Government Warning wording does not match the required verbatim text.' },
      { key: 'casingBoldOk',     msg: '"GOVERNMENT WARNING" must be in all capitals and bold.' },
      { key: 'fontSizeOk',       msg: 'Warning text is below the minimum required type size.' },
      { key: 'contrastOk',       msg: 'Warning text contrast is below the legibility threshold.' },
      { key: 'separateAndApart', msg: 'Warning must appear separate and apart from other label copy.' },
    ];
    for (const { key, msg } of gwFails) {
      if (gw[key] === false) {
        reasons.push({
          id: `gw:${String(key)}`,
          text: msg + ' (27 CFR 16.21 / 16.22)',
          category: 'warning', severity: 'flag', defaultChecked: true,
        });
      }
    }
  }
  return reasons;
}

export interface BuildDraftInput {
  mode: DecisionMode;
  app: ApplicationData | null;
  result: VerificationResult;
  selectedReasons: SuggestedReason[];
  freeText: string;
  imageQuality: ImageQuality | null;
}

export function buildDraft({ mode, app, result, selectedReasons, freeText, imageQuality }: BuildDraftInput): string {
  const brand = app?.brandName || 'Untitled label';
  const cola = app?.colaNumber ? `COLA #${app.colaNumber}` : '';
  const ts = new Date().toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' });
  const head = `${brand}${cola ? ' · ' + cola : ''}`;
  const decisionText =
    mode === 'approve'      ? 'APPROVED' :
    mode === 'reject'       ? 'REJECTED — request label correction' :
                              'BLOCKED — better image requested';

  const lines: string[] = [
    `Label: ${head}`,
    `Decision: ${decisionText}`,
    `Reviewed: ${ts}`,
    `Agent: [your name]`,
    '',
  ];

  if (mode === 'approve') {
    const fc = result.fields.reduce<Record<string, number>>(
      (a, f) => (a[f.status] = (a[f.status] || 0) + 1, a),
      { match: 0, likely: 0, flag: 0 },
    );
    lines.push(`Verification summary: ${fc.match} match · ${fc.likely} likely · ${fc.flag} flag.`);
    if (result.governmentWarning?.verbatimMatch) lines.push('Government Warning: compliant (27 CFR 16.21 / 16.22).');
    lines.push('All compliance checks satisfied. Label is approved for use.');
  }

  if (mode === 'reject') {
    lines.push('Reasons for rejection:');
    for (const r of selectedReasons) lines.push('  • ' + r.text);
    if (freeText.trim()) {
      lines.push('', 'Additional notes:', '  ' + freeText.trim().replace(/\n/g, '\n  '));
    }
    lines.push('', 'Action: applicant must correct the items above and resubmit.');
  }

  if (mode === 'requestImage') {
    const score = imageQuality?.score != null ? Math.round(imageQuality.score * 100) : '—';
    lines.push(`Image quality score: ${score}%${imageQuality?.legible === false ? ' (not legible)' : ''}.`);
    if (imageQuality?.note) lines.push('OCR note: ' + imageQuality.note);
    if (freeText.trim()) {
      lines.push('', 'Notes for the applicant:', '  ' + freeText.trim().replace(/\n/g, '\n  '));
    } else {
      lines.push('', 'Please re-upload a higher-resolution scan of the front and back panels.');
    }
  }

  return lines.join('\n');
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────
export interface DecisionPanelProps {
  result: VerificationResult;
  applicationData: ApplicationData | null;
  streamingDone: boolean;
}

type Mode = 'idle' | DecisionMode | 'saved';

export default function DecisionPanel({ result, applicationData, streamingDone }: DecisionPanelProps) {
  const [mode, setMode]             = useState<Mode>('idle');
  const [reasons, setReasons]       = useState<Record<string, boolean>>({});
  const [freeText, setFreeText]     = useState('');
  const [draft, setDraft]           = useState('');
  const [draftDirty, setDraftDirty] = useState(false);
  const [savedEntry, setSavedEntry] = useState<DecisionEntry | null>(null);
  const [liveMsg, setLiveMsg]       = useState('');

  useEffect(() => {
    setMode('idle');
    setReasons({});
    setFreeText('');
    setDraft('');
    setDraftDirty(false);
    setSavedEntry(null);
  }, [applicationData]);

  const suggestedReasons = useMemo(() => deriveReasons(result), [result]);
  useEffect(() => {
    setReasons(prev => {
      const next = { ...prev };
      let changed = false;
      for (const r of suggestedReasons) {
        if (!(r.id in next)) { next[r.id] = r.defaultChecked; changed = true; }
      }
      return changed ? next : prev;
    });
  }, [suggestedReasons]);

  const selectedReasons = suggestedReasons.filter(r => reasons[r.id]);

  const fc = result.fields.reduce<Record<'match' | 'likely' | 'flag', number>>(
    (a, f) => (a[f.status] = (a[f.status] || 0) + 1, a),
    { match: 0, likely: 0, flag: 0 },
  );
  const gw = result.governmentWarning;
  const gwFailing = gw ? (
    gw.present === false ||
    gw.verbatimMatch === false ||
    gw.casingBoldOk === false ||
    gw.fontSizeOk === false ||
    gw.contrastOk === false ||
    gw.separateAndApart === false
  ) : false;
  const imageBad = result.imageQuality ? (!result.imageQuality.legible || result.imageQuality.score < 0.6) : false;

  const primary: DecisionMode =
    imageBad ? 'requestImage' :
    (fc.flag > 0 || gwFailing) ? 'reject' :
    'approve';

  useEffect(() => {
    if (mode === 'idle' || mode === 'saved') return;
    if (draftDirty) return;
    setDraft(buildDraft({
      mode,
      app: applicationData,
      result,
      selectedReasons,
      freeText,
      imageQuality: result.imageQuality,
    }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, JSON.stringify(reasons), freeText, applicationData, result.fields.length, result.governmentWarning, result.imageQuality]);

  function startMode(m: DecisionMode) {
    setMode(m);
    setDraftDirty(false);
    setLiveMsg(
      m === 'approve'       ? 'Approval form opened. Review the auto-drafted log entry.' :
      m === 'reject'        ? 'Rejection form opened. Choose reasons or add your own.' :
                              'Request-better-image form opened.',
    );
  }
  function cancelMode() { setMode('idle'); setDraftDirty(false); setLiveMsg('Decision form closed.'); }
  function toggleReason(id: string) { setReasons(prev => ({ ...prev, [id]: !prev[id] })); }

  function handleSave() {
    if (mode === 'idle' || mode === 'saved') return;
    if (mode === 'reject' && selectedReasons.length === 0 && !freeText.trim()) {
      setLiveMsg('Add at least one reason before recording a rejection.');
      return;
    }
    const entry: DecisionEntry = {
      brand: applicationData?.brandName || '',
      colaNumber: applicationData?.colaNumber,
      decision: mode,
      reasons: selectedReasons.map(r => r.text),
      freeText: freeText.trim(),
      logEntry: draft,
      savedAt: new Date().toISOString(),
      agent: '[your name]',
    };
    saveDecisionLocally(entry);
    setSavedEntry(entry);
    setMode('saved');
    setLiveMsg(`Decision recorded: ${entry.decision}. Log saved.`);
  }

  if (!streamingDone && mode === 'idle') {
    return (
      <section className="decision" aria-labelledby="dec-h">
        <header className="decision__header">
          <h3 id="dec-h" className="decision__title">Decision</h3>
          <p className="decision__sub">Available once verification finishes streaming.</p>
        </header>
      </section>
    );
  }

  return (
    <section className="decision" aria-labelledby="dec-h">
      <p className="sr-only" role="status" aria-live="polite">{liveMsg}</p>

      <header className="decision__header">
        <div>
          <p className="decision__kicker">Step 3 · Decision</p>
          <h3 id="dec-h" className="decision__title">Record your decision</h3>
          <p className="decision__sub">
            {primary === 'approve'      && 'All checks passed. Approving is the recommended next action.'}
            {primary === 'reject'       && `${fc.flag + (gwFailing ? 1 : 0)} unresolved issue${(fc.flag + (gwFailing ? 1 : 0)) === 1 ? '' : 's'} — review the suggested reasons.`}
            {primary === 'requestImage' && 'The image is too low-quality for a confident review.'}
          </p>
        </div>
      </header>

      {mode === 'idle' && (
        <ActionsGrid
          primary={primary}
          onApprove={() => startMode('approve')}
          onReject={() => startMode('reject')}
          onRequest={() => startMode('requestImage')}
          flagCount={fc.flag}
          gwFailing={gwFailing}
          imageBad={imageBad}
        />
      )}

      {mode === 'approve' && (
        <ApproveForm
          flagCount={fc.flag}
          matchCount={fc.match}
          gwFailing={gwFailing}
          draft={draft}
          setDraft={(v) => { setDraft(v); setDraftDirty(true); }}
          onCancel={cancelMode}
          onSave={handleSave}
        />
      )}

      {mode === 'reject' && (
        <RejectForm
          suggestedReasons={suggestedReasons}
          reasons={reasons}
          toggleReason={toggleReason}
          freeText={freeText}
          setFreeText={setFreeText}
          draft={draft}
          setDraft={(v) => { setDraft(v); setDraftDirty(true); }}
          canSave={selectedReasons.length > 0 || !!freeText.trim()}
          onCancel={cancelMode}
          onSave={handleSave}
        />
      )}

      {mode === 'requestImage' && (
        <RequestImageForm
          imageQuality={result.imageQuality}
          freeText={freeText}
          setFreeText={setFreeText}
          draft={draft}
          setDraft={(v) => { setDraft(v); setDraftDirty(true); }}
          onCancel={cancelMode}
          onSave={handleSave}
        />
      )}

      {mode === 'saved' && savedEntry && <SavedState entry={savedEntry} />}
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────
interface ActionsGridProps {
  primary: DecisionMode;
  onApprove: () => void;
  onReject: () => void;
  onRequest: () => void;
  flagCount: number;
  gwFailing: boolean;
  imageBad: boolean;
}

function ActionsGrid({ primary, onApprove, onReject, onRequest, flagCount, gwFailing, imageBad }: ActionsGridProps) {
  const blocked = flagCount > 0 || gwFailing;
  const issues = flagCount + (gwFailing ? 1 : 0);
  return (
    <div className="decision__grid">
      <ActionCard
        tone="match" isPrimary={primary === 'approve'} Icon={IconCheck}
        title="Approve"
        body={blocked
          ? `Resolve ${issues} issue${issues === 1 ? '' : 's'} first, or approve with an override note.`
          : 'All compliance checks pass.'}
        button={blocked ? 'Approve with override' : 'Approve label'}
        onClick={onApprove}
      />
      <ActionCard
        tone="flag" isPrimary={primary === 'reject'} Icon={IconClose}
        title="Reject (with reasons)"
        body={`${flagCount} flagged field${flagCount === 1 ? '' : 's'}${gwFailing ? ' + Government Warning issues' : ''}. Suggested reasons are pre-checked.`}
        button="Open reject form"
        onClick={onReject}
      />
      <ActionCard
        tone="likely" isPrimary={primary === 'requestImage'} Icon={IconImage}
        title="Request better image"
        body={imageBad
          ? 'Image quality is below threshold — OCR may have missed details.'
          : 'Optional. Use when fields are illegible in any region.'}
        button="Request a higher-res image"
        onClick={onRequest}
      />
    </div>
  );
}

interface ActionCardProps {
  tone: 'match' | 'flag' | 'likely';
  isPrimary: boolean;
  Icon: typeof IconCheck;
  title: string;
  body: string;
  button: string;
  onClick: () => void;
}

function ActionCard({ tone, isPrimary, Icon, title, body, button, onClick }: ActionCardProps) {
  return (
    <div className={`decision__card decision__card--${tone}${isPrimary ? ' decision__card--primary' : ''}`}>
      {isPrimary && <span className="decision__primary-tag">Recommended</span>}
      <span className={`decision__icon decision__icon--${tone}`} aria-hidden="true">
        <Icon size={20} strokeWidth={2.5} />
      </span>
      <h4 style={{ margin: '0 0 6px' }}>{title}</h4>
      <p style={{ margin: '0 0 16px', color: 'var(--color-ink-muted)', fontSize: 'var(--fs-14)' }}>{body}</p>
      <Button variant={isPrimary ? 'primary' : 'secondary'} onClick={onClick} style={{ width: '100%' }}>
        {button}
      </Button>
    </div>
  );
}

interface FormShellProps {
  title: string;
  children: React.ReactNode;
  onCancel: () => void;
  onSave: () => void;
  saveLabel: string;
  saveTone: 'match' | 'flag' | 'likely';
  canSave: boolean;
  canSaveHint?: string;
}

function FormShell({ title, children, onCancel, onSave, saveLabel, saveTone, canSave, canSaveHint }: FormShellProps) {
  return (
    <div className="decision__form">
      <header className="decision__form-head">
        <h4 style={{ margin: 0 }}>{title}</h4>
        <button type="button" className="btn btn--ghost" onClick={onCancel}>
          <IconArrowL size={16} /> Back to decision options
        </button>
      </header>
      <div className="decision__form-body">{children}</div>
      <footer className="decision__form-foot">
        {!canSave && canSaveHint && (
          <p style={{ margin: 0, color: 'var(--color-ink-muted)', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <IconInfo size={16} /> {canSaveHint}
          </p>
        )}
        <span style={{ flex: 1 }} />
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button variant={saveTone === 'flag' ? 'danger' : 'primary'} disabled={!canSave} onClick={onSave} icon={IconCheck}>
          {saveLabel}
        </Button>
      </footer>
    </div>
  );
}

function LogTextarea({ draft, setDraft }: { draft: string; setDraft: (v: string) => void }) {
  return (
    <>
      <label htmlFor="dec-log" className="sr-only">Auto-drafted log entry — fully editable</label>
      <textarea
        id="dec-log"
        className="field__input decision__draft"
        rows={10}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        spellCheck
        style={{ maxWidth: '100%', fontFamily: 'var(--font-mono)', fontSize: 13, lineHeight: 1.55 }}
      />
      <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--color-ink-subtle)' }}>
        The draft updates automatically until you edit it; your edits are preserved from that point on.
      </p>
    </>
  );
}

interface ApproveFormProps {
  flagCount: number; matchCount: number; gwFailing: boolean;
  draft: string; setDraft: (v: string) => void; onCancel: () => void; onSave: () => void;
}

function ApproveForm({ flagCount, matchCount, gwFailing, draft, setDraft, onCancel, onSave }: ApproveFormProps) {
  const blocked = flagCount > 0 || gwFailing;
  return (
    <FormShell title="Approve label" onCancel={onCancel} onSave={onSave}
      saveLabel="Confirm & save log" saveTone="match" canSave>
      {blocked ? (
        <Alert variant="warning" title="Heads up — you're approving despite issues">
          <p>There are unresolved findings. Add a brief override note to the log below so the audit trail explains the call.</p>
        </Alert>
      ) : (
        <Alert variant="success" title="Clean review">
          <p>{matchCount} field{matchCount === 1 ? '' : 's'} matched. Government Warning is compliant. Recording this decision will mark the label approved.</p>
        </Alert>
      )}
      <LogTextarea draft={draft} setDraft={setDraft} />
    </FormShell>
  );
}

interface RejectFormProps {
  suggestedReasons: SuggestedReason[];
  reasons: Record<string, boolean>;
  toggleReason: (id: string) => void;
  freeText: string; setFreeText: (v: string) => void;
  draft: string; setDraft: (v: string) => void;
  canSave: boolean; onCancel: () => void; onSave: () => void;
}

function RejectForm({ suggestedReasons, reasons, toggleReason, freeText, setFreeText, draft, setDraft, canSave, onCancel, onSave }: RejectFormProps) {
  return (
    <FormShell title="Reject label" onCancel={onCancel} onSave={onSave}
      saveLabel="Confirm rejection" saveTone="flag" canSave={canSave}
      canSaveHint="Select at least one reason or add a note below.">
      <h5 className="decision__sect">Suggested reasons</h5>
      {suggestedReasons.length === 0 ? (
        <p style={{ color: 'var(--color-ink-muted)' }}>No automated suggestions — add your own reason below.</p>
      ) : (
        <ul className="decision__reasons" aria-label="Suggested rejection reasons">
          {suggestedReasons.map(r => (
            <li key={r.id} className={`decision__reason decision__reason--${r.severity}`}>
              <label style={{ display: 'flex', alignItems: 'flex-start', gap: 12, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={!!reasons[r.id]}
                  onChange={() => toggleReason(r.id)}
                  style={{ width: 20, height: 20, marginTop: 1, flexShrink: 0 }}
                />
                <span>
                  <span className={`decision__reason-cat decision__reason-cat--${r.category}`}>
                    {r.category === 'field' ? 'Field' : 'Warning'}
                  </span>
                  <span style={{ marginLeft: 8 }}>{r.text}</span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}

      <h5 className="decision__sect">Additional notes (optional)</h5>
      <label htmlFor="dec-free" className="sr-only">Additional rejection notes</label>
      <textarea
        id="dec-free"
        className="field__input"
        rows={3}
        placeholder="Anything else the applicant should know…"
        value={freeText}
        onChange={(e) => setFreeText(e.target.value)}
        style={{ maxWidth: '100%', fontFamily: 'var(--font-sans)', lineHeight: 1.5 }}
      />

      <h5 className="decision__sect">Log entry</h5>
      <LogTextarea draft={draft} setDraft={setDraft} />
    </FormShell>
  );
}

interface RequestImageFormProps {
  imageQuality: ImageQuality | null;
  freeText: string; setFreeText: (v: string) => void;
  draft: string; setDraft: (v: string) => void;
  onCancel: () => void; onSave: () => void;
}

function RequestImageForm({ imageQuality, freeText, setFreeText, draft, setDraft, onCancel, onSave }: RequestImageFormProps) {
  const score = imageQuality ? Math.round(imageQuality.score * 100) : null;
  return (
    <FormShell title="Request a better image" onCancel={onCancel} onSave={onSave}
      saveLabel="Send request & save log" saveTone="likely" canSave>
      <Alert variant="info" title={score != null ? `Image quality score: ${score}%` : 'Image quality unknown'}>
        <p>
          {imageQuality?.note ?? 'OCR is operating below its usable threshold for some regions of the label.'}
        </p>
      </Alert>
      <h5 className="decision__sect">Message to the applicant</h5>
      <label htmlFor="dec-img-msg" className="sr-only">Message to the applicant</label>
      <textarea
        id="dec-img-msg"
        className="field__input"
        rows={3}
        placeholder="e.g., Please upload a scan of at least 300 DPI showing the front, back, and warning panels."
        value={freeText}
        onChange={(e) => setFreeText(e.target.value)}
        style={{ maxWidth: '100%', fontFamily: 'var(--font-sans)', lineHeight: 1.5 }}
      />
      <h5 className="decision__sect">Log entry</h5>
      <LogTextarea draft={draft} setDraft={setDraft} />
    </FormShell>
  );
}

function SavedState({ entry }: { entry: DecisionEntry }) {
  const verbose =
    entry.decision === 'approve' ? 'Approval' :
    entry.decision === 'reject'  ? 'Rejection' :
                                   'Request for better image';
  return (
    <div className="decision__saved">
      <Alert variant="success" title={`${verbose} recorded. Log saved.`}>
        <p>
          A copy is staged locally in this browser (key <code>{DECISIONS_STORAGE_KEY}</code>).
          The backend POST endpoint will replace local-storage staging when it ships.
        </p>
      </Alert>

      <details className="decision__details">
        <summary>View saved log entry</summary>
        <pre style={{
          margin: '12px 0 0', padding: 16, background: 'var(--color-bg-alt)',
          borderRadius: 4, fontFamily: 'var(--font-mono)', fontSize: 13, lineHeight: 1.55,
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
        }}>{entry.logEntry}</pre>
      </details>

      <h4 style={{ margin: '24px 0 12px' }}>What next?</h4>
      <div className="decision__nextsteps">
        <Link to="/upload" className="btn btn--secondary" onClick={() => verifyStore.reset()}>
          Verify another label <IconArrowR size={16} />
        </Link>
        <Link to="/batch" className="btn btn--ghost">Go to batch review</Link>
        <Link to="/upload" className="btn btn--ghost" onClick={() => verifyStore.reset()}>Start over</Link>
      </div>
    </div>
  );
}
