# Submission Email — TTB Label Verification Take-Home

> Drop-in copy. ~250 words.

---

**Subject:** TTB Label Verification — Take-Home Submission

Hello,

The prototype is deployed and the source is on GitHub.

- **Live:** https://ttb-label-verification-ebon.vercel.app
- **Repo:** https://github.com/vsiwach/ttb-label-verification

Four things to know:

- **Privacy-first, extensible.** The four PII-class fields (brand, class, bottler, country) come from a fine-tuned Qwen 2.5-VL 7B LoRA we host ourselves. The public-text fields fixed verbatim by 27 CFR — the Government Warning, ABV, net contents — come from Anthropic Haiku in parallel. Inference sits behind an interface; swap commodity APIs (Sonnet, Gemini, Bedrock GovCloud) without touching the UI.

- **Fine-tuning beat the frontier API.** On a 2,000-row TTB-stratified holdout, our LoRA hit **78.0 % field accuracy vs 37.2 % for Haiku zero-shot** — biggest delta on class & type (+72 pp) where the TTB vocabulary is invisible to frontier models. Trained weights ship with the repo; Treasury can validate independently.

- **A deterministic rules engine, not the model, decides.** Every match / likely / flag verdict cites the exact 27 CFR section. Same input always yields the same regulatory determination. Survives model swaps.

- **Designed for the 73-year-old user Sarah described.** Three-state verdicts with icon + text (never color alone), streaming UI so the first useful render lands at **~0.6 s** (vs the prior vendor's 30–40 s that killed adoption), unified batch review with visible Approve / Reject / Request-image buttons, 44 × 44 targets, keyboard shortcuts for power users.

Every P0 in the brief is met; the [DESIGN doc §10](https://github.com/vsiwach/ttb-label-verification/blob/main/docs/DESIGN.md) walks the handful of deliberate divergences with rationale.

**Start with the 13-slide deck — 10 minutes:** [`docs/TTB_Executive_Presentation.pptx`](https://github.com/vsiwach/ttb-label-verification/blob/main/docs/TTB_Executive_Presentation.pptx). Happy to demo live and walk any trade-off in detail.

Best,
Vikram
