import { useState } from 'react';
import { Link } from 'react-router-dom';
import Alert from '../components/Alert';
import Button from '../components/Button';
import Card from '../components/Card';
import FieldRow from '../components/FieldRow';
import FileDropzone from '../components/FileDropzone';
import StatusBadge from '../components/StatusBadge';
import { SkeletonBlock, SkeletonLine } from '../components/Skeleton';
import { IconArrowR, IconCheck, IconUpload } from '../components/icons';

function SgSection({ id, title, anchor, children }: { id: string; title: string; anchor: string; children: React.ReactNode }) {
  return (
    <section className="sg-section" id={id}>
      <h2>
        <span>{title}</span>
        <span className="anchor">{anchor}</span>
      </h2>
      {children}
    </section>
  );
}

export default function StyleGuidePage() {
  const [picked, setPicked] = useState<File | null>(null);

  return (
    <div className="container container--narrow">
      <p style={{ marginBottom: 8 }}><span className="tag">Internal</span></p>
      <h1>Component styleguide</h1>
      <p style={{ fontSize: 'var(--fs-18)', color: 'var(--color-ink-muted)', maxWidth: 'none', marginBottom: 32 }}>
        Every primitive in <code>src/components/</code>, with sample data. Tab from the
        top — focus must land on every interactive control in a logical order with a clearly visible focus ring.
      </p>

      <nav aria-label="Styleguide sections" style={{
        display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 40,
        padding: 12, background: 'var(--color-bg-alt)', borderRadius: 6,
      }}>
        {[
          ['Status badges', 'badges'],
          ['Buttons',       'buttons'],
          ['Cards',         'cards'],
          ['Dropzone',      'dropzone'],
          ['Field row',     'fieldrow'],
          ['Skeletons',     'skel'],
          ['Alerts',        'alerts'],
        ].map(([label, hash]) => (
          <a key={hash} href={`#${hash}`} style={{ fontWeight: 600 }}>{label}</a>
        ))}
      </nav>

      <SgSection id="badges" title="StatusBadge" anchor="<StatusBadge status … />">
        <p>Three states. Color + icon + text — never color alone. Each badge has an aria-label that fully describes its meaning.</p>
        <div className="sg-card">
          <div className="sg-row">
            <StatusBadge status="match" />
            <StatusBadge status="likely" />
            <StatusBadge status="flag" />
          </div>
        </div>
      </SgSection>

      <SgSection id="buttons" title="Button" anchor="<Button variant … />">
        <p>Four variants × two sizes. All ≥ 44 × 44 (default min-height). Disabled is non-color (cursor, aria-disabled, lower contrast).</p>
        <div className="sg-card" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="sg-row">
            <Button>Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="danger">Danger</Button>
            <Button disabled>Disabled</Button>
          </div>
          <div className="sg-row">
            <Button size="lg" icon={IconUpload}>Upload label</Button>
            <Button size="lg" variant="secondary" trailingIcon={IconArrowR}>Continue</Button>
            <Button size="lg" variant="ghost" icon={IconCheck}>Confirm all matches</Button>
          </div>
        </div>
      </SgSection>

      <SgSection id="cards" title="Card" anchor="<Card title titleLevel … />">
        <p>Bordered/padded container. Optional title at a configurable heading level so the page outline stays correct.</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16 }}>
          <Card title="With H3 title" titleLevel={3} headerSlot={<span className="tag">Default</span>}>
            <p style={{ margin: 0 }}>Body content. Use <code>titleLevel</code> to set the heading level for a correct document outline.</p>
          </Card>
          <Card>
            <h3 style={{ margin: '0 0 8px' }}>No header slot</h3>
            <p style={{ margin: 0 }}>Just children. Useful for free-form layouts.</p>
          </Card>
        </div>
      </SgSection>

      <SgSection id="dropzone" title="FileDropzone" anchor="<FileDropzone accept … />">
        <p>Drag-and-drop or click. Validates MIME against <code>accept</code>; rejection surfaces as a plain-language field error.</p>
        <FileDropzone
          accept="image/jpeg,image/png"
          onFiles={(files) => setPicked(files[0])}
          label="Drop a label image"
          hint="JPEG or PNG, up to 20 MB."
          buttonLabel="Choose a file…"
        />
        {picked && (
          <div style={{ marginTop: 16 }}>
            <Alert variant="success" title="File received">
              <p>{picked.name} — {(picked.size / 1024).toFixed(1)} KB · {picked.type}</p>
            </Alert>
          </div>
        )}
      </SgSection>

      <SgSection id="fieldrow" title="FieldRow" anchor="<FieldRow status … />">
        <p>One verification field with evidence crop + declared/extracted values + status. Renders a one-click Confirm for likely matches and a Review affordance for flags.</p>
        <Card>
          <FieldRow
            fieldName="Brand name"
            declaredValue="Sample Vineyards"
            extractedValue="Sample Vineyards"
            status="match"
            regulationCite="27 CFR 4.32(a)"
          />
          <FieldRow
            fieldName="Alcohol content"
            declaredValue="14.5% alc/vol"
            extractedValue="14.5% ALC/VOL"
            status="likely"
            regulationCite="27 CFR 4.36"
            onConfirm={() => {}}
          />
          <FieldRow
            fieldName="Government warning"
            declaredValue="Required verbatim text"
            extractedValue="GOVERNMENT WARNING (1)… [font size 1.4mm]"
            status="flag"
            regulationCite="27 CFR 16.21/16.22"
          />
        </Card>
      </SgSection>

      <SgSection id="skel" title="SkeletonLine / SkeletonBlock" anchor="<SkeletonLine / SkeletonBlock />">
        <p>Shimmer placeholders. The animation is disabled automatically when the user has <em>prefers-reduced-motion: reduce</em> set.</p>
        <div className="sg-card" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 24 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <SkeletonLine width="60%" height={18} />
            <SkeletonLine />
            <SkeletonLine width="92%" />
            <SkeletonLine width="78%" />
          </div>
          <SkeletonBlock height={108} />
        </div>
      </SgSection>

      <SgSection id="alerts" title="Alert / Callout" anchor="<Alert variant … />">
        <p>Plain-language messages. Error and warning variants use role=alert so screen readers announce them.</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Alert variant="info" title="Image will be downscaled">
            Your file is reduced to 2048 px on the long edge in your browser before upload, so the verification stays under 5 seconds.
          </Alert>
          <Alert variant="success" title="11 of 11 fields match" onDismiss={() => {}}>
            Ready to approve. No agent action required.
          </Alert>
          <Alert variant="warning" title="2 likely matches">
            One-click confirm needed before approval — see the rows highlighted below.
          </Alert>
          <Alert variant="error" title="The government warning could not be located">
            Re-upload a higher-resolution image, or flag the label as non-compliant. Reference: <code>27 CFR 16.21/16.22</code>.
          </Alert>
        </div>
      </SgSection>

      <hr className="divider" />
      <Link to="/upload" className="btn btn--ghost" style={{ textDecoration: 'none' }}>
        Back to the upload flow <IconArrowR size={16} />
      </Link>
    </div>
  );
}
