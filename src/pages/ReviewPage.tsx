import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { ApplicationData, VerificationField, VerificationResult } from '../api/types';
import { useVerifyStore } from '../store/verifyStore';
import Alert from '../components/Alert';
import Button from '../components/Button';
import Card from '../components/Card';
import GovernmentWarningPanel from '../components/GovernmentWarningPanel';
import StatusBadge from '../components/StatusBadge';
import {
  buildDraft, deriveReasons, saveDecisionLocally,
  type DecisionEntry, type DecisionMode, type SuggestedReason,
} from '../components/DecisionPanel';
import {
  IconArrowL, IconArrowR, IconCheck, IconClose, IconImage, IconInfo,
} from '../components/icons';

function isTypingTarget(t: EventTarget | null): boolean {
  if (!t || !(t instanceof HTMLElement)) return false;
  if (t.isContentEditable) return true;
  const tag = t.tagName.toLowerCase();
  if (tag === 'textarea' || tag === 'select') return true;
  if (tag === 'input') {
    const type = ((t as HTMLInputElement).type || 'text').toLowerCase();
    return !['checkbox', 'radio', 'button', 'submit', 'reset'].includes(type);
  }
  return false;
}

/** Empty ApplicationData for batch items without a known declared source.
 *  Replaces the old guessAppData() synthetic placeholder. */
function emptyAppData(): ApplicationData {
  return {
    colaNumber: '',
    brandName: '',
    classType: '',
    alcoholContent: '',
    netContents: '',
    bottlerNameAddress: '',
    beverageType: 'spirits',
  };
}

/** Per-item application data from the batch picker; empty if the user
 *  dropped their own file (no picker entry). */
function appDataFor(item: { fileName?: string }, session: { appDataByFile?: Record<string, ApplicationData> } | null | undefined): ApplicationData {
  const fn = item.fileName || '';
  if (session?.appDataByFile && fn in session.appDataByFile) return session.appDataByFile[fn];
  return emptyAppData();
}

export default function ReviewPage() {
  const navigate = useNavigate();
  const state = useVerifyStore();
  const session = state.reviewSession;

  const [confirmations, setConfirmations] = useState<Record<string, boolean>>({});
  const [decisions, setDecisions]         = useState<Record<string, DecisionEntry>>({});
  // Seed from session.startIndex so clicking a specific row in the batch
  // dashboard drops the user directly into that item's review, with
  // Next/Prev spanning the whole batch. Defaults to 0 for the "Review
  // all" button.
  const [index, setIndex]                 = useState(session?.startIndex ?? 0);
  const [showHelp, setShowHelp]           = useState(false);
  const [rejectingId, setRejectingId]     = useState<string | null>(null);
  const [liveMsg, setLiveMsg]             = useState('');
  // Per-item free-text notes the agent can type into the visible action
  // panel before clicking Approve / Request image. Flows into the
  // decision log entry. Reject reuses InlineRejectForm's own freeText
  // (pre-filled from this when the form opens). Reset on item change so
  // notes don't leak between labels.
  const [notes, setNotes]                 = useState('');
  const headingRef = useRef<HTMLHeadingElement>(null);

  if (!session || session.queue.length === 0) {
    return (
      <div className="container container--narrow" style={{ paddingTop: 40 }}>
        <Card>
          <h1 style={{ marginBottom: 8 }}>Nothing to review</h1>
          <p style={{ color: 'var(--color-ink-muted)' }}>
            Start a batch first; the review flow steps through items that need attention.
          </p>
          <Button icon={IconArrowL} onClick={() => navigate('/batch')}>Go to batch</Button>
        </Card>
      </div>
    );
  }

  const queue = session.queue;
  const total = queue.length;
  const item  = queue[index];
  const done  = Object.keys(decisions).length;

  const tally = useMemo(() => {
    const t = { approve: 0, reject: 0, requestImage: 0 };
    for (const id of Object.keys(decisions)) {
      const m = decisions[id].decision;
      if (m in t) t[m as keyof typeof t]++;
    }
    return t;
  }, [decisions]);

  const liveResult: VerificationResult | null = useMemo(() => {
    if (!item) return null;
    if (!confirmations[item.id]) return item.result;
    return {
      ...item.result,
      fields: item.result.fields.map(f =>
        f.status === 'likely' ? { ...f, status: 'match' as const } : f
      ),
    };
  }, [item, confirmations]);

  const advance = useCallback(() => {
    setRejectingId(null);
    setNotes('');
    setIndex(i => Math.min(i + 1, total));
  }, [total]);
  const previous = useCallback(() => {
    setRejectingId(null);
    setNotes('');
    setIndex(i => Math.max(0, i - 1));
  }, []);
  const exit = useCallback(() => navigate('/batch'), [navigate]);

  const recordDecision = (mode: DecisionMode, opts: { selectedReasons?: SuggestedReason[]; freeText?: string } = {}) => {
    if (!item || !liveResult) return;
    const reasons = opts.selectedReasons || [];
    const freeText = opts.freeText || '';
    const log = buildDraft({
      mode,
      app: session.shared ?? appDataFor(item, session),
      result: liveResult,
      selectedReasons: reasons,
      freeText,
      imageQuality: liveResult.imageQuality,
    });
    const entry: DecisionEntry = {
      brand: session.shared?.brandName ?? appDataFor(item, session).brandName,
      colaNumber: session.shared?.colaNumber,
      decision: mode,
      reasons: reasons.map(r => r.text),
      freeText,
      logEntry: log,
      savedAt: new Date().toISOString(),
      agent: '[your name]',
    };
    saveDecisionLocally(entry);
    setDecisions(prev => ({ ...prev, [item.id]: entry }));
    const friendly = mode === 'approve' ? 'Approved' : mode === 'reject' ? 'Rejected' : 'Image re-requested';
    setLiveMsg(`${friendly}. Advancing.`);
    advance();
  };

  const quickApprove = () => recordDecision('approve', { freeText: notes });
  const quickRequestImage = () => recordDecision('requestImage', { freeText: notes });
  const quickConfirmAll = () => {
    if (!item) return;
    setConfirmations(prev => ({ ...prev, [item.id]: true }));
    setLiveMsg('All likely matches confirmed for this item.');
  };
  const openReject = () => {
    if (!item) return;
    setRejectingId(item.id);
    setLiveMsg('Rejection form open. Pick reasons or add notes, then press Enter to confirm.');
  };

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isTypingTarget(e.target)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (rejectingId && rejectingId === item?.id) {
        if (k === '?' || (k === '/' && e.shiftKey)) { e.preventDefault(); setShowHelp(s => !s); }
        return;
      }
      if (k === 'escape') { e.preventDefault(); exit(); return; }
      if (index >= total) return;
      if (k === 'a') { e.preventDefault(); quickApprove(); return; }
      if (k === 'r') { e.preventDefault(); openReject(); return; }
      if (k === 'i') { e.preventDefault(); quickRequestImage(); return; }
      if (k === 'c') { e.preventDefault(); quickConfirmAll(); return; }
      if (k === 'n' || k === 'arrowright') { e.preventDefault(); advance(); return; }
      if (k === 'p' || k === 'arrowleft')  { e.preventDefault(); previous(); return; }
      if (k === '?' || (k === '/' && e.shiftKey)) { e.preventDefault(); setShowHelp(s => !s); return; }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, total, item, liveResult, rejectingId]);

  useEffect(() => {
    headingRef.current?.focus();
    if (item) setLiveMsg(`Item ${index + 1} of ${total}: ${item.fileName}.`);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index]);

  if (index >= total) {
    return (
      <CompletionScreen
        total={total}
        tally={tally}
        decisionsCount={done}
        onBack={() => navigate('/batch')}
        onReplay={() => setIndex(0)}
      />
    );
  }

  if (!item || !liveResult) return null;

  const statusForItem = decisions[item.id]?.decision;
  const liveCounts = {
    match:  liveResult.fields.filter(f => f.status === 'match').length,
    likely: liveResult.fields.filter(f => f.status === 'likely').length,
    flag:   liveResult.fields.filter(f => f.status === 'flag').length,
  };
  const hasLikely = liveResult.fields.some(f => f.status === 'likely');
  const brandTitle = session.shared?.brandName || appDataFor(item, session).brandName;

  return (
    <div className="container">
      <p className="sr-only" role="status" aria-live="polite">{liveMsg}</p>

      <header className="review-top">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
            <span className="tag">Confirm next</span>
            <span style={{ color: 'var(--color-ink-muted)', fontSize: 'var(--fs-14)' }}>
              Item {index + 1} of {total} needing attention
            </span>
          </div>
          <h1 ref={headingRef} tabIndex={-1} style={{ margin: 0, outline: 'none' }}>
            {brandTitle}
          </h1>
          <div style={{ marginTop: 4, color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
            {item.fileName}
          </div>
        </div>
        <div className="review-top__tally" aria-label="Decisions so far">
          <Stat Icon={IconCheck} tone="match"  label="Approved"            value={tally.approve} />
          <Stat Icon={IconClose} tone="flag"   label="Rejected"            value={tally.reject} />
          <Stat Icon={IconImage} tone="likely" label="Image re-requested"  value={tally.requestImage} />
          <Stat Icon={IconInfo}  tone="info"   label="Pending"             value={total - done} />
        </div>
      </header>

      <div
        style={{ height: 6, borderRadius: 4, background: 'var(--color-bg-alt)', overflow: 'hidden', marginTop: 12, marginBottom: 16 }}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={index}
        aria-label="Review progress"
      >
        <div style={{ width: `${(index / total) * 100}%`, height: '100%', background: 'var(--color-primary)', transition: 'width 240ms ease' }} />
      </div>

      <KeyboardLegend
        onApprove={quickApprove}
        onReject={openReject}
        onRequest={quickRequestImage}
        onConfirmAll={quickConfirmAll}
        onPrev={previous}
        onNext={advance}
        onExit={exit}
        showHelp={showHelp}
        setShowHelp={setShowHelp}
        hasLikely={hasLikely}
        index={index}
      />

      <div className="review-body">
        <aside aria-label="Label image">
          <div className="card card--flush" style={{ overflow: 'hidden' }}>
            <img
              // Prefer the per-file data URL the picker captured (the actual
              // label the agent picked). Fall back to whatever the backend
              // returned in thumbnailUrl. Either way, no broken image icon.
              src={session.imageDataUrlByFile?.[item.fileName] || item.thumbnailUrl || ''}
              alt={`Label preview — ${item.fileName}`}
              style={{ display: 'block', width: '100%', height: 'auto', maxHeight: 420, objectFit: 'contain', background: '#f5f5f5' }}
            />
            <div className="card__header" style={{ borderBottom: 0, borderTop: '1px solid var(--color-line)' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.fileName}</div>
                <div style={{ color: 'var(--color-ink-muted)', fontSize: 13 }}>
                  Image quality {Math.round((liveResult.imageQuality?.score || 0) * 100)}%
                </div>
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            {liveCounts.match  > 0 && <StatusBadge status="match" />}
            {liveCounts.likely > 0 && <StatusBadge status="likely" />}
            {liveCounts.flag   > 0 && <StatusBadge status="flag" />}
          </div>
        </aside>

        <section aria-labelledby="fields-h">
          <h2 id="fields-h" style={{ margin: '0 0 12px', fontSize: 'var(--fs-20)' }}>Field verdicts</h2>
          <div className="card card--flush">
            {[...liveResult.fields]
              .sort((a, b) => ({ flag: 0, likely: 1, match: 2 } as Record<string, number>)[a.status] - ({ flag: 0, likely: 1, match: 2 } as Record<string, number>)[b.status])
              .map(f => (
                <FieldCompactRow
                  key={f.fieldName}
                  field={f}
                  onFlag={openReject}
                  onConfirm={f.status === 'likely' ? () => quickConfirmAll() : undefined}
                />
              ))}
          </div>

          {liveResult.governmentWarning && (
            <GovernmentWarningPanel gw={liveResult.governmentWarning} />
          )}
        </section>
      </div>

      {!statusForItem && rejectingId !== item.id && (
        <ActionPanel
          liveCounts={liveCounts}
          gwFailing={!!liveResult.governmentWarning &&
            (!liveResult.governmentWarning.present
             || !liveResult.governmentWarning.verbatimMatch
             || !liveResult.governmentWarning.casingBoldOk)}
          imageBad={!!liveResult.imageQuality && !liveResult.imageQuality.legible}
          notes={notes}
          setNotes={setNotes}
          onApprove={quickApprove}
          onReject={openReject}
          onRequestImage={quickRequestImage}
        />
      )}

      {rejectingId === item.id && (
        <InlineRejectForm
          result={liveResult}
          initialNotes={notes}
          onCancel={() => setRejectingId(null)}
          onConfirm={(selectedReasons, freeText) => recordDecision('reject', { selectedReasons, freeText })}
        />
      )}

      {statusForItem && (
        <div style={{ marginTop: 20 }}>
          <Alert
            variant={statusForItem === 'approve' ? 'success' : statusForItem === 'reject' ? 'error' : 'info'}
            title={`${statusForItem === 'approve' ? 'Approved' : statusForItem === 'reject' ? 'Rejected' : 'Image re-requested'} for this item — staged in the log`}
          >
            <p>Use <span className="kbd">N</span> or <span className="kbd">→</span> to move on, or <span className="kbd">P</span> / <span className="kbd">←</span> to revisit.</p>
          </Alert>
        </div>
      )}

      <div className="review-foot">
        <Button variant="secondary" icon={IconArrowL} onClick={previous} disabled={index === 0}>Previous</Button>
        <Button variant="ghost" onClick={exit}>Exit to dashboard</Button>
        <span style={{ flex: 1 }} />
        <Button trailingIcon={IconArrowR} onClick={advance}>
          {statusForItem ? (index === total - 1 ? 'Finish review' : 'Next') : (index === total - 1 ? 'Skip & finish' : 'Skip')}
        </Button>
      </div>
    </div>
  );
}

function FieldCompactRow({ field, onFlag, onConfirm }: {
  field: VerificationField;
  /** Fires when the user clicks a Flag pill — opens the per-item reject
   *  dialog with this field's reason pre-checked (along with any other
   *  flagged reasons). The agent expects the pill to be actionable. */
  onFlag?: () => void;
  /** Fires when the user clicks a Likely pill — confirms this field
   *  (and any other likelies) inline without opening a dialog. */
  onConfirm?: () => void;
}) {
  // Decide what click does based on status: Flag → open reject; Likely →
  // quick-confirm. Match is passive (no action — it's already passing).
  const handler =
    field.status === 'flag'   ? onFlag
    : field.status === 'likely' ? onConfirm
    : undefined;
  const actionLabel =
    field.status === 'flag'   ? `Open reject dialog (${field.fieldName} flagged)`
    : field.status === 'likely' ? `Confirm this likely match`
    : undefined;
  return (
    <div className="result-row" data-status={field.status}>
      <div style={{ padding: '12px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 220px', minWidth: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--color-ink-muted)' }}>
              {field.fieldName}
            </div>
            <div style={{ fontSize: 14, color: 'var(--color-ink-muted)', marginTop: 2 }}>
              Declared <strong style={{ color: 'var(--color-ink)' }}>{field.declaredValue}</strong>
              {' '}· Extracted <strong style={{ color: 'var(--color-ink)' }}>{field.extractedValue}</strong>
            </div>
          </div>
          <StatusBadge status={field.status} onClick={handler} actionLabel={actionLabel} />
        </div>
      </div>
    </div>
  );
}

interface KeyboardLegendProps {
  onApprove: () => void; onReject: () => void; onRequest: () => void; onConfirmAll: () => void;
  onPrev: () => void; onNext: () => void; onExit: () => void;
  showHelp: boolean; setShowHelp: (fn: (s: boolean) => boolean) => void;
  hasLikely: boolean; index: number;
}

function KeyboardLegend({ onApprove, onReject, onRequest, onConfirmAll, onPrev, onNext, onExit, showHelp, setShowHelp, hasLikely, index }: KeyboardLegendProps) {
  return (
    <div className="review-keys" aria-label="Keyboard shortcuts">
      <button type="button" className="review-keys__btn" onClick={onApprove} aria-label="Approve and advance (A)">
        <span className="kbd">A</span> Approve
      </button>
      <button type="button" className="review-keys__btn" onClick={onReject} aria-label="Reject — open reasons (R)">
        <span className="kbd">R</span> Reject
      </button>
      <button type="button" className="review-keys__btn" onClick={onRequest} aria-label="Request better image (I)">
        <span className="kbd">I</span> Request image
      </button>
      <button type="button" className="review-keys__btn" onClick={onConfirmAll} disabled={!hasLikely}
        aria-label="Confirm all likely matches on this item (C)">
        <span className="kbd">C</span> Confirm all likely
      </button>
      <span className="review-keys__sep" aria-hidden="true">·</span>
      <button type="button" className="review-keys__btn" onClick={onPrev} disabled={index === 0} aria-label="Previous item (P)">
        <span className="kbd">P</span> Prev
      </button>
      <button type="button" className="review-keys__btn" onClick={onNext} aria-label="Next item (N)">
        <span className="kbd">N</span> Next
      </button>
      <button type="button" className="review-keys__btn" onClick={onExit} aria-label="Exit to dashboard (Esc)">
        <span className="kbd">Esc</span> Exit
      </button>
      <button type="button" className="review-keys__btn review-keys__help" onClick={() => setShowHelp(s => !s)} aria-expanded={showHelp}>
        <span className="kbd">?</span> {showHelp ? 'Hide' : 'Help'}
      </button>

      {showHelp && (
        <div className="review-help">
          <h4 style={{ margin: '0 0 8px' }}>Keyboard reference</h4>
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'grid', gap: 4 }}>
            <li><span className="kbd">A</span> Approve and advance to next attention item</li>
            <li><span className="kbd">R</span> Open the reject form (pre-checked reasons; Cmd+Enter to confirm)</li>
            <li><span className="kbd">I</span> Request a better image and advance</li>
            <li><span className="kbd">C</span> Confirm all likely matches on the current item</li>
            <li><span className="kbd">N</span> / <span className="kbd">→</span> Next item</li>
            <li><span className="kbd">P</span> / <span className="kbd">←</span> Previous item</li>
            <li><span className="kbd">Esc</span> Exit to dashboard</li>
            <li><span className="kbd">?</span> Toggle this help</li>
          </ul>
          <p style={{ margin: '12px 0 0', color: 'var(--color-ink-muted)', fontSize: 13 }}>
            Shortcuts don't fire while you're typing in a textarea or input.
          </p>
        </div>
      )}
    </div>
  );
}

interface ActionPanelProps {
  liveCounts: { match: number; likely: number; flag: number };
  gwFailing: boolean;
  imageBad: boolean;
  notes: string;
  setNotes: (v: string) => void;
  onApprove: () => void;
  onReject: () => void;
  onRequestImage: () => void;
}

/** The visible decision panel at the bottom of each review item. Mirrors
 *  the single-label /result page's ActionsGrid so non-keyboard users
 *  have an obvious way to commit a verdict with comments. Keyboard
 *  shortcuts (A / R / I) call the same handlers — both paths converge
 *  on recordDecision() and the notes textarea below flows into the
 *  decision log entry. */
function ActionPanel({
  liveCounts, gwFailing, imageBad,
  notes, setNotes,
  onApprove, onReject, onRequestImage,
}: ActionPanelProps) {
  const issues = liveCounts.flag + (gwFailing ? 1 : 0);
  const blocked = issues > 0;
  const approveLabel = blocked ? 'Approve with override' : 'Approve label';
  const approveTitle = blocked
    ? `Resolve ${issues} issue${issues === 1 ? '' : 's'} first, or add an override note below and approve anyway.`
    : 'All compliance checks pass. Add any final notes below if you like.';

  return (
    <section
      aria-labelledby="review-actions-h"
      className="card"
      style={{
        marginTop: 24, padding: 20,
        border: '1px solid var(--color-line)',
        background: 'var(--color-surface, #fff)',
      }}
    >
      <header style={{ marginBottom: 12 }}>
        <h3 id="review-actions-h" style={{ margin: 0, fontSize: 'var(--fs-20)' }}>Record your decision</h3>
        <p style={{ margin: '4px 0 0', color: 'var(--color-ink-muted)', fontSize: 'var(--fs-14)' }}>
          Use the buttons below, or the keyboard shortcuts at the top of the page.
          Notes you type here flow into the audit log.
        </p>
      </header>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 12,
          marginBottom: 16,
        }}
      >
        <ActionButton
          tone="match"
          title="Approve"
          subtitle={approveTitle}
          buttonLabel={approveLabel}
          shortcut="A"
          onClick={onApprove}
        />
        <ActionButton
          tone="flag"
          title="Reject (with reasons)"
          subtitle={
            liveCounts.flag > 0 || gwFailing
              ? `${liveCounts.flag} flagged field${liveCounts.flag === 1 ? '' : 's'}${gwFailing ? ' + Government Warning issue' : ''}. Reasons are pre-checked in the form.`
              : 'Opens the reject form. Pick reasons or add a note, then confirm.'
          }
          buttonLabel="Open reject form"
          shortcut="R"
          onClick={onReject}
        />
        <ActionButton
          tone="likely"
          title="Request a better image"
          subtitle={imageBad
            ? 'Image quality is below threshold — OCR may have missed details.'
            : 'Optional. Use when any region is illegible.'}
          buttonLabel="Request higher-res image"
          shortcut="I"
          onClick={onRequestImage}
        />
      </div>

      <label htmlFor="review-notes" className="field__label">
        Notes (optional)
      </label>
      <textarea
        id="review-notes"
        className="field__input"
        rows={3}
        placeholder="Anything to add to the audit log — override rationale, applicant message, internal context…"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        style={{ maxWidth: '100%', fontFamily: 'var(--font-sans)', lineHeight: 1.5 }}
      />
      <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--color-ink-subtle, var(--color-ink-muted))' }}>
        Notes are saved with the decision when you Approve or Request image.
        If you Reject, this text pre-fills the reject form's notes field.
      </p>
    </section>
  );
}

interface ActionButtonProps {
  tone: 'match' | 'flag' | 'likely';
  title: string;
  subtitle: string;
  buttonLabel: string;
  shortcut: string;
  onClick: () => void;
}

function ActionButton({ tone, title, subtitle, buttonLabel, shortcut, onClick }: ActionButtonProps) {
  const variant: 'primary' | 'danger' | 'secondary' =
    tone === 'match' ? 'primary' : tone === 'flag' ? 'danger' : 'secondary';
  return (
    <div
      style={{
        padding: 16,
        borderRadius: 8,
        border: `1px solid var(--status-${tone}-fg, var(--color-line))`,
        background: `var(--status-${tone}-bg, var(--color-bg-alt))`,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'space-between' }}>
        <strong style={{ fontSize: 'var(--fs-16)' }}>{title}</strong>
        <span className="kbd" aria-hidden="true">{shortcut}</span>
      </div>
      <p style={{ margin: 0, fontSize: 'var(--fs-14)', color: 'var(--color-ink-muted)', minHeight: 40 }}>
        {subtitle}
      </p>
      <Button variant={variant} onClick={onClick} style={{ width: '100%' }}>
        {buttonLabel}
      </Button>
    </div>
  );
}

interface InlineRejectFormProps {
  result: VerificationResult;
  initialNotes?: string;
  onCancel: () => void;
  onConfirm: (reasons: SuggestedReason[], freeText: string) => void;
}

function InlineRejectForm({ result, initialNotes, onCancel, onConfirm }: InlineRejectFormProps) {
  const suggested = useMemo(() => deriveReasons(result), [result]);
  const [reasons, setReasons] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    for (const r of suggested) init[r.id] = r.defaultChecked;
    return init;
  });
  const [freeText, setFreeText] = useState(initialNotes ?? '');
  const formRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (formRef.current) {
      const first = formRef.current.querySelector<HTMLElement>('input, textarea, button');
      first?.focus();
    }
  }, []);

  const selected = suggested.filter(r => reasons[r.id]);
  const canSubmit = selected.length > 0 || freeText.trim().length > 0;

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      if (canSubmit) onConfirm(selected, freeText);
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      onCancel();
    }
  }

  return (
    <div className="card" ref={formRef} onKeyDown={handleKey}
      style={{ marginTop: 20, padding: 20, border: '2px solid var(--status-flag-fg)' }}
      role="dialog" aria-labelledby="rj-h">
      <h3 id="rj-h" style={{ margin: '0 0 12px' }}>Reject this label</h3>
      <p style={{ margin: '0 0 16px', color: 'var(--color-ink-muted)' }}>
        Reasons derived from the verdict are pre-checked. Adjust as needed and press
        <span className="kbd" style={{ margin: '0 4px' }}>⌘</span><span className="kbd">Enter</span> to confirm, or <span className="kbd">Esc</span> to cancel.
      </p>
      <ul className="decision__reasons" aria-label="Suggested rejection reasons">
        {suggested.map(r => (
          <li key={r.id} className={`decision__reason decision__reason--${r.severity}`}>
            <label style={{ display: 'flex', alignItems: 'flex-start', gap: 12, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={!!reasons[r.id]}
                onChange={() => setReasons(p => ({ ...p, [r.id]: !p[r.id] }))}
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

      <div style={{ marginTop: 16 }}>
        <label htmlFor="rj-free" className="field__label">Additional notes (optional)</label>
        <textarea
          id="rj-free"
          className="field__input"
          rows={2}
          value={freeText}
          onChange={(e) => setFreeText(e.target.value)}
          style={{ maxWidth: '100%', fontFamily: 'var(--font-sans)', lineHeight: 1.5 }}
        />
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
        <Button variant="ghost" onClick={onCancel}>Cancel (Esc)</Button>
        <Button variant="danger" disabled={!canSubmit} onClick={() => onConfirm(selected, freeText)} icon={IconCheck}>
          Confirm rejection (⌘⏎)
        </Button>
      </div>
    </div>
  );
}

function Stat({ Icon, tone, label, value }: { Icon: typeof IconCheck; tone: 'match' | 'flag' | 'likely' | 'info'; label: string; value: number }) {
  const bg = tone === 'info' ? 'var(--color-bg-alt)' : `var(--status-${tone}-bg)`;
  const fg = tone === 'info' ? 'var(--color-ink)'    : `var(--status-${tone}-fg)`;
  return (
    <div className="review-stat" style={{ background: bg, color: fg }}>
      <Icon size={14} aria-hidden="true" />
      <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700, fontSize: 'var(--fs-18)' }}>{value}</span>
      <span style={{ fontSize: 12 }}>{label}</span>
    </div>
  );
}

function CompletionScreen({ total, tally, decisionsCount, onBack, onReplay }: {
  total: number;
  tally: { approve: number; reject: number; requestImage: number };
  decisionsCount: number;
  onBack: () => void;
  onReplay: () => void;
}) {
  const skipped = total - decisionsCount;
  return (
    <div className="container container--narrow" style={{ paddingTop: 32 }}>
      <Card padding={32}>
        <span style={{
          width: 56, height: 56, borderRadius: 28,
          background: 'var(--status-match-bg)', color: 'var(--status-match-fg)',
          display: 'grid', placeItems: 'center', marginBottom: 16,
        }} aria-hidden="true">
          <IconCheck size={28} strokeWidth={2.5} />
        </span>
        <h1 style={{ marginBottom: 8 }}>Review complete</h1>
        <p style={{ color: 'var(--color-ink-muted)', fontSize: 'var(--fs-18)' }}>
          You stepped through {total} item{total === 1 ? '' : 's'} needing attention.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 12, marginTop: 24 }}>
          <SummaryStat tone="match"  value={tally.approve}      label="Approved" />
          <SummaryStat tone="flag"   value={tally.reject}       label="Rejected" />
          <SummaryStat tone="likely" value={tally.requestImage} label="Image re-requested" />
          <SummaryStat tone="info"   value={skipped}            label="Skipped" />
        </div>
        <div style={{ display: 'flex', gap: 12, marginTop: 32, flexWrap: 'wrap' }}>
          <Button onClick={onBack} icon={IconArrowL}>Back to dashboard</Button>
          {skipped > 0 && <Button variant="secondary" onClick={onReplay}>Replay from start</Button>}
        </div>
      </Card>
    </div>
  );
}

function SummaryStat({ tone, value, label }: { tone: 'match' | 'flag' | 'likely' | 'info'; value: number; label: string }) {
  const bg = tone === 'info' ? 'var(--color-bg-alt)' : `var(--status-${tone}-bg)`;
  const fg = tone === 'info' ? 'var(--color-ink)'    : `var(--status-${tone}-fg)`;
  return (
    <div style={{ padding: 16, background: bg, borderRadius: 8, textAlign: 'center', color: fg }}>
      <div style={{ fontSize: 'var(--fs-30)', fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
      <div style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em' }}>{label}</div>
    </div>
  );
}
