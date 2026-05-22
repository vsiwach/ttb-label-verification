# Security & Data Handling

The TTB label verification prototype runs on the principle of "process in
memory, persist nothing sensitive." This document records what the prototype
actually does today and what would change for a production deployment.

## Prototype posture (current)

| Concern | What we do |
|---|---|
| Label images | Read into memory for one request, never written to disk. Discarded when the request ends. |
| Field values & warning text | Returned to the requesting client; **not** logged. Logs only carry the brand name, beverage type, response group, and elapsed time. |
| Application data (COLA) | Held in memory for the duration of the request. Not stored. |
| Evidence crops | JPEG-encoded in memory only. Served from `/crops/{id}` with a 10-minute TTL and `Cache-Control: no-store`. Expire and are dropped automatically; never written to disk. |
| Cloud provider data retention | Anthropic API requests by default do not retain customer prompts for model training. For production we recommend the Zero Data Retention agreement. |
| Audit log | None in the prototype (matches "process, don't persist" posture). |
| Authentication / RBAC | None — single-user, local prototype. |
| TLS | The prototype binds plain HTTP on localhost. Any non-local deployment must terminate TLS at a reverse proxy (e.g. nginx, Caddy) or hosting platform. |

## Production scaffold (OFF by default — not wired)

The shapes below are intentional gaps the production deployment would fill in:

- **Structured audit log** — who verified what, when, the decision, and the
  regulation citations. **Never the PII / field values themselves.** Pipe to
  the agency's existing SIEM.
- **Role-based access control** — agent / supervisor / admin scopes. Bearer
  tokens issued by the agency IdP; FastAPI dependency injects the role.
- **Configurable retention policy** — for the rare cases where retention is
  required (e.g. a flagged label held for human review), an explicit, scoped
  store with TTL and access logging — never the default path.
- **Input limits & abuse protection** — max file size, max batch size, IP
  rate limiting at the proxy.
- **TLS everywhere** — terminate at the edge; on-prem path stays inside the
  agency network boundary.

## On-prem / air-gapped mode

`INFERENCE_MODE=onprem` makes ZERO outbound network calls. All inference
stays inside the agency's accreditation boundary (e.g. a hardened VM /
VNet inside Azure Government). Tesseract OCR runs locally; if/when a
self-hosted Phi-3.5-vision or Qwen2.5-VL endpoint is configured at
`ONPREM_VLM_URL`, that traffic stays on the internal network too.

## Quick verification checklist

- `grep -r "logger\." backend/app/` should show no log statements emitting
  field values, warning text, image bytes, or application addresses.
- The `/crops/{id}` route MUST set `Cache-Control: no-store`.
- The crop store MUST be in-memory; check `backend/app/image_pipeline.py`
  for any `open()` calls writing to disk (there should be none).
