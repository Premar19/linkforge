// Load test for GET /r/{code} — the cached redirect path.
//
// Two traffic patterns, controlled by the MODE env var, run against the
// SAME deployed code (no feature flags, no code branching for the test):
//
//   MODE=miss  each request picks a random code from a large pre-seeded
//              pool (see seed_links.py). With enough codes and a short
//              enough test, repeats are rare, so requests are overwhelmingly
//              cache MISSES — this is the "before Redis" baseline, since
//              almost every request still round-trips to Postgres.
//
//   MODE=hit   every request hits the SAME single code. After the very
//              first request populates the cache, every subsequent request
//              is a Redis HIT — this is the "after Redis" case.
//
// Usage:
//   k6 run -e MODE=miss -e BASE_URL=http://localhost:8000 -e VUS=20 -e DURATION=30s redirect_test.js
//   k6 run -e MODE=hit  -e BASE_URL=http://localhost:8000 -e VUS=20 -e DURATION=30s redirect_test.js
import http from 'k6/http';
import { check } from 'k6';
import { SharedArray } from 'k6/data';

const MODE = __ENV.MODE || 'miss';
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

const codes = new SharedArray('codes', function () {
  return JSON.parse(open('./seeded_codes.json'));
});

export const options = {
  scenarios: {
    default: {
      executor: 'constant-vus',
      vus: Number(__ENV.VUS || 20),
      duration: __ENV.DURATION || '30s',
    },
  },
};

export default function () {
  const code = MODE === 'hit' ? codes[0] : codes[Math.floor(Math.random() * codes.length)];
  // redirects: 0 — we're measuring OUR redirect response, not following it
  // all the way to example.com (which would add unrelated internet latency
  // and isn't what we're testing).
  const res = http.get(`${BASE_URL}/r/${code}`, { redirects: 0 });
  check(res, { 'status is 307': (r) => r.status === 307 });
}
