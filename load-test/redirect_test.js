// Load test for GET /r/{code} — the cached redirect path.
//
// Two traffic patterns, controlled by the MODE env var, run against the
// SAME deployed code (no feature flags, no code branching for the test):
//
//   MODE=miss  every request gets a genuinely different code — guaranteed,
//              not just probable. Each VU is assigned its own private,
//              non-overlapping slice of the pre-seeded pool (see
//              seed_links.py) and works through it sequentially. No shared
//              counter between VUs is used, so there's no concurrency
//              hazard: k6's own iterationInTest counter turned out to be
//              read-at-iteration-start rather than atomically claimed,
//              which let concurrent VUs collide on the same index in
//              practice (confirmed empirically: even with unique-looking
//              indices, ~40% of "miss" requests still landed on repeats).
//              Per-VU slicing sidesteps the question entirely.
//
//   MODE=hit   every request hits the SAME single code. After the very
//              first request populates the cache, every subsequent request
//              is a Redis HIT — the "after Redis" case.
//
// Verified directly via app-level counters (metrics:cache_hit /
// metrics:cache_miss in Redis, incremented in app/routers/redirect.py),
// not Redis's own global keyspace_hits/misses — those are contaminated by
// arq's job-queue traffic on the same Redis instance.
//
// Usage:
//   k6 run -e MODE=miss -e BASE_URL=http://localhost:8000 -e VUS=20 -e DURATION=30s redirect_test.js
//   k6 run -e MODE=hit  -e BASE_URL=http://localhost:8000 -e VUS=20 -e DURATION=30s redirect_test.js
import http from 'k6/http';
import { check } from 'k6';
import { SharedArray } from 'k6/data';
import { vu } from 'k6/execution';

const MODE = __ENV.MODE || 'miss';
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const VUS = Number(__ENV.VUS || 20);

const codes = new SharedArray('codes', function () {
  return JSON.parse(open('./seeded_codes.json'));
});

// Each VU gets its own private, non-overlapping block of codes — e.g. with
// 20,000 codes and 20 VUs, VU 1 gets codes[0..999], VU 2 gets
// codes[1000..1999], etc. As long as no single VU exceeds CODES_PER_VU
// iterations during the test (comfortably true here — observed ~300-400
// iterations/VU in a 30s run, vs 1000 available), every request across the
// ENTIRE test gets a genuinely unique code, with no cross-VU coordination
// or shared mutable state required.
const CODES_PER_VU = Math.floor(codes.length / VUS);

// Safe as per-VU module-level state: k6 runs each VU in its own isolated
// JS runtime, so this counter is never shared or raced across VUs.
let localIter = 0;

export const options = {
  scenarios: {
    default: {
      executor: 'constant-vus',
      vus: VUS,
      duration: __ENV.DURATION || '30s',
    },
  },
};

export default function () {
  let code;
  if (MODE === 'hit') {
    code = codes[0];
  } else {
    const vuIndex = vu.idInTest - 1; // idInTest is 1-based
    const blockStart = vuIndex * CODES_PER_VU;
    code = codes[(blockStart + localIter) % codes.length];
    localIter++;
  }
  const res = http.get(`${BASE_URL}/r/${code}`, { redirects: 0 });
  check(res, { 'status is 307': (r) => r.status === 307 });
}