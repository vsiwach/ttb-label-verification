const H4 = {
  color: '#fff', fontSize: 14, textTransform: 'uppercase' as const,
  letterSpacing: '.06em', margin: '0 0 8px',
};

// External link helper — opens in a new tab with secure-default rel.
function Ext({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
  );
}

export default function Footer() {
  return (
    <footer className="site-footer" role="contentinfo">
      <div className="site-footer__inner">
        <div>
          <h3 className="site-footer__title">TTB Label Verification</h3>
          <p className="site-footer__meta" style={{ maxWidth: 'none' }}>
            Hybrid AI label-compliance review for the Alcohol and Tobacco
            Tax and Trade Bureau: Modal Qwen v2 LoRA on our infrastructure
            for the 4 TTB-trained PII fields, Anthropic Haiku for the
            27 CFR 16.21 public-text fields, and a deterministic Python
            rules engine that cites every match / likely / flag verdict.
          </p>
          <p className="site-footer__meta" style={{ marginTop: 16 }}>
            Section 508 / WCAG 2.1–2.2 AA compliant. USWDS visual conventions.
          </p>
        </div>
        <div>
          <h4 style={H4}>Regulations cited</h4>
          <ul>
            <li><Ext href="https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-4">27 CFR Part 4 — Wine</Ext></li>
            <li><Ext href="https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5">27 CFR Part 5 — Spirits</Ext></li>
            <li><Ext href="https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-7">27 CFR Part 7 — Malt</Ext></li>
            <li><Ext href="https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16">27 CFR Part 16 — Health warning</Ext></li>
          </ul>
        </div>
        <div>
          <h4 style={H4}>Project</h4>
          <ul>
            <li><Ext href="https://github.com/vsiwach/ttb-label-verification">Source — GitHub repo</Ext></li>
            <li><Ext href="https://github.com/vsiwach/ttb-label-verification/releases/tag/v0.1.0">v0.1.0 release · Qwen v2 weights + eval pack</Ext></li>
            <li><Ext href="https://ttbonline.gov/colasonline/publicSearchColasBasic.do">TTB Public COLA Registry (data source)</Ext></li>
            <li><Ext href="https://modal.com/apps/vsiwach/main/deployed/ttb-qwen-extractor-v2">Modal Qwen v2 deploy (private)</Ext></li>
          </ul>
        </div>
      </div>
    </footer>
  );
}
