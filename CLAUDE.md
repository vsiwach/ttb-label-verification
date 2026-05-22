# TTB Label Verification

Frontend: React + Vite + TypeScript in src/. It calls a typed API and currently runs
on mock data (USE_MOCK in src/api/client.ts; mock when VITE_API_BASE_URL is empty).

We are now building a Python + FastAPI backend that implements the SAME contract.
The contract is defined in: src/api/types.ts, src/api/client.ts, src/api/mockData.ts,
src/api/ttbRules.ts  (read these — they are the source of truth).

Contract essentials:
- POST /api/verify (multipart: image + applicationData JSON) -> full VerificationResult JSON, NOT streaming.
- POST /api/verify-batch (multipart: images[] + optional applicationData) -> BatchItemResult[].
- Mirror groupFor() bucketing on the server. Keep VERBATIM_GOVERNMENT_WARNING identical.

Architecture rule: the AI model ONLY extracts + scores what it reads; a deterministic
27 CFR rules engine makes every match/likely/flag decision and cites the regulation.
Use current post-2020 citations (spirits 5.63, wine 4.32, malt 7.63, warning 16.21/16.22).
Inference behind a swappable interface: INFERENCE_MODE = mock | cloud | onprem.
