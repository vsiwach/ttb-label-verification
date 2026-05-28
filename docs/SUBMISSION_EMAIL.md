# Submission Email — TTB Label Verification Take-Home

> Drop-in copy. Scannable in ~60 s.

---

**Subject:** TTB Label Verification — Take-Home Submission

Hi Sam,

Thanks for the opportunity. I've attached the **executive slide deck** (13 slides, ~10 min) covering the design and headline results. The prototype is deployed and the source is on GitHub:

- **Live demo:** https://ttb-label-verification-ebon.vercel.app
- **Repo:** https://github.com/vsiwach/ttb-label-verification

---

### Four key features

**1 · Privacy-first, with a commodity-API extension**

- The four PII-class fields (brand, class, bottler, country of origin) come from a **Qwen 2.5-VL 7B LoRA we host ourselves** — PII never leaves our boundary
- The 27 CFR public-text fields (Government Warning, ABV, net contents) come from **Anthropic Haiku in parallel** — small public values, nothing to protect
- Swap commodity providers (Sonnet, Gemini, Bedrock GovCloud) with **one environment variable** — verifier code unchanged

**2 · Fine-tuning beat the frontier API**

- **78.0 %** field accuracy on our LoRA vs **37.2 %** for Haiku zero-shot (2,000-row TTB-stratified holdout — **2.1× better**)
- Biggest delta on **class & type: +72 pp** — TTB vocabulary like "SPANISH GRAPE BRANDY FB" is invisible to frontier models, learned cleanly by the LoRA
- Trained weights ship with the repo — Treasury can validate independently

**3 · Deterministic rules engine — not the model — makes every call**

- Every match / likely / flag verdict **cites the exact 27 CFR section**
- Same input always yields the same regulatory determination
- Survives model swaps — the legal logic is in Python, not in weights

**4 · Designed for the user Sarah described**

- Three-state verdicts: icon + text labels (**never color alone**)
- Streaming UI — first useful render at **~0.6 s** (vs the prior vendor's 30–40 s that killed adoption)
- Unified batch review — visible Approve / Reject / Request-image buttons + notes textarea + keyboard shortcuts
- **44 × 44 px** touch targets, ≥16 px body, ≥4.5:1 contrast, ARIA live regions

---

Every P0 in the brief is met; the [DESIGN doc §10](https://github.com/vsiwach/ttb-label-verification/blob/main/docs/DESIGN.md#10-prd-alignment--whats-built-what-diverged-whats-gap) walks the handful of deliberate divergences with rationale.

Happy to demo live and walk any trade-off in detail.

Best,
Vikram
