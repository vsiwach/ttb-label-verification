// Fire-and-forget Modal warmup on page mount + periodic heartbeat.
// /health on the FastAPI side pings the Modal /health_web endpoint with a
// 5s budget. If Modal is cold, that probe triggers load_model() server-side
// (~30-60s) so by the time the agent finishes filling the form and clicks
// Verify, the GPU container is warm and the verify hits the <5s warm path.
//
// We don't await — the page render shouldn't block on the warmup. Errors
// are swallowed; the actual verify call surfaces any real failures.
//
// Modal's scaledown_window is 5 min: if no requests arrive for 5 min the
// container scales to zero and the next verify hits cold-start. Agents
// often fill the form for longer than that, so a single page-mount ping
// isn't enough — we also fire a heartbeat every 4 min while the page is
// open (under the scaledown window) so the container stays alive
// throughout long form sessions.

import { API_BASE_URL } from '../api/client';

let lastWarmAt = 0;
const WARM_COOLDOWN_MS    = 60_000;        // don't spam /health on every nav
const HEARTBEAT_INTERVAL  = 4 * 60 * 1000; // 4 min — under Modal's 5-min scaledown
let heartbeatTimer: ReturnType<typeof setInterval> | null = null;

function pingHealth(): void {
  if (!API_BASE_URL) return;
  const base = API_BASE_URL.replace(/\/api$/, '');
  fetch(`${base}/health`, { method: 'GET', cache: 'no-store' }).catch(() => {
    // swallow — the verify call will surface real backend errors
  });
}

export function preWarmModal(): void {
  if (!API_BASE_URL) return;
  const now = Date.now();
  if (now - lastWarmAt >= WARM_COOLDOWN_MS) {
    lastWarmAt = now;
    pingHealth();
  }
  // Start the heartbeat exactly once per page load. The timer is cleared
  // automatically when the tab is hidden (visibilitychange handler) to
  // avoid burning Modal compute on backgrounded tabs.
  if (heartbeatTimer == null && typeof window !== 'undefined') {
    heartbeatTimer = setInterval(() => {
      if (document.visibilityState === 'visible') pingHealth();
    }, HEARTBEAT_INTERVAL);
    document.addEventListener('visibilitychange', () => {
      // When the tab comes back into focus after being away, ping right
      // away so the container is warm before the agent gets back to it.
      if (document.visibilityState === 'visible') pingHealth();
    });
  }
}
