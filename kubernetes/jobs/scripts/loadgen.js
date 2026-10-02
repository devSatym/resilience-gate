import http from 'k6/http';
import encoding from 'k6/encoding';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// This script is intentionally inert until a caller supplies BASE_URL (and,
// for paid traffic, SIGNER_URL). That makes `k6 run` without reviewed job
// configuration fail before opening a socket.
const TESTNET_NETWORK = 'eip155:72344';
const MAX_SIGNER_WALLETS = 3;
const MAX_RUN_DURATION_MS = 30 * 60 * 1000;

const signSuccessRate = new Rate('sign_success_rate');
const paymentSettledRate = new Rate('payment_settled_rate');
const shorten201Rate = new Rate('shorten_201_rate');
const shorten402Rate = new Rate('shorten_402_rate');
const shorten409Rate = new Rate('shorten_409_rate');
const shorten5xxRate = new Rate('shorten_5xx_rate');
const redirectOkRate = new Rate('redirect_ok_rate');
const independentRedirectOkRate = new Rate('independent_redirect_ok_rate');
const endToEndSuccessRate = new Rate('end_to_end_success_rate');
const endToEndDuration = new Trend('end_to_end_duration_ms', true);
const baselineGetSuccessRate = new Rate('baseline_get_success_rate');
const baseline5xxRate = new Rate('baseline_5xx_rate');
const baselineGetDuration = new Trend('baseline_get_duration_ms', true);

function environment(name, fallback = '') {
  return String(__ENV[name] === undefined ? fallback : __ENV[name]).trim();
}

function fail(message) {
  throw new Error(message);
}

function positiveInteger(name, value, maximum) {
  if (!/^\d+$/.test(String(value))) fail(`${name} must be a positive integer`);
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 1 || parsed > maximum) {
    fail(`${name} must be between 1 and ${maximum}`);
  }
  return parsed;
}

function positiveNumber(name, value, maximum) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0 || parsed > maximum) {
    fail(`${name} must be greater than 0 and no more than ${maximum}`);
  }
  return parsed;
}

function parseDurationMs(name, value, maximumMs) {
  const match = /^(\d+(?:\.\d+)?)(ms|s|m|h)$/.exec(String(value).trim());
  if (!match) fail(`${name} must use ms, s, m, or h (received ${value})`);
  const multipliers = { ms: 1, s: 1000, m: 60000, h: 3600000 };
  const parsed = Number(match[1]) * multipliers[match[2]];
  if (!Number.isFinite(parsed) || parsed <= 0 || parsed > maximumMs) {
    fail(`${name} must be greater than 0 and no more than ${maximumMs}ms`);
  }
  return parsed;
}

function parseBoolean(name, value) {
  if (value === 'true') return true;
  if (value === 'false') return false;
  fail(`${name} must be true or false`);
}

function normaliseHttpUrl(name, value) {
  if (!/^https?:\/\/[^\s/]+(?:\/[^\s]*)?$/i.test(value)) {
    fail(`${name} must be an explicit http(s) URL`);
  }
  return value.replace(/\/+$/, '');
}

const BASE_URL = environment('BASE_URL');
const TRAFFIC_MODE = environment('TRAFFIC_MODE', 'paid');
const SIGNER_URL = environment('SIGNER_URL');
const NETWORK_CAIP2 = environment('NETWORK_CAIP2', TESTNET_NETWORK);
const SERVICE_WALLET = environment('SERVICE_WALLET_ADDRESS');
const SBC_CONTRACT = environment(
  'SBC_CONTRACT_ADDRESS',
  '0x33ad9e4bd16b69b5bfded37d8b5d9ff9aba014fb',
);
const SBC_AMOUNT = positiveInteger('SBC_AMOUNT', environment('SBC_AMOUNT', '1000'), Number.MAX_SAFE_INTEGER);
const PAYMENT_ENABLED = parseBoolean('PAYMENT_ENABLED', environment('PAYMENT_ENABLED', 'true'));
const LOAD_PROFILE = environment('LOAD_PROFILE', 'closed-loop');
const VUS = positiveInteger('VUS', environment('VUS', '1'), MAX_SIGNER_WALLETS);
const ARRIVAL_RATE = positiveInteger('ARRIVAL_RATE', environment('ARRIVAL_RATE', '1'), 600);
const ARRIVAL_TIME_UNIT = environment('ARRIVAL_TIME_UNIT', '1m');
const SLEEP_SECONDS = positiveNumber('SLEEP_SECONDS', environment('SLEEP_SECONDS', '1'), 60);
const PRECHECK_TIMEOUT = environment('PRECHECK_TIMEOUT', '5s');
const DURATION = environment('DURATION', '5m');
const PAYMENT_BUFFER = positiveInteger(
  'PRECHECK_BALANCE_BUFFER_PAYMENTS',
  environment('PRECHECK_BALANCE_BUFFER_PAYMENTS', '5'),
  1000,
);
const REDIRECT_PROBE_URL = environment('REDIRECT_PROBE_URL');
const DEV_BASELINE_URL = 'http://url-shortener-dev.url-shortener-dev.svc.cluster.local';
const MAX_BASELINE_DURATION_MS = 90 * 1000;
const SUMMARY_MARKER = 'RESILIENCE_GATE_K6_SUMMARY ';
const PAID_TRAFFIC_READY_MARKER = 'RESILIENCE_GATE_PAID_TRAFFIC_READY v1';

let scenarios;
let thresholds;
let paidTrafficReadyReported = false;

if (TRAFFIC_MODE === 'unpaid-baseline') {
  scenarios = {
    unpaid_baseline: {
      executor: 'constant-arrival-rate',
      exec: 'baselineFlow',
      rate: ARRIVAL_RATE,
      timeUnit: ARRIVAL_TIME_UNIT,
      duration: DURATION,
      preAllocatedVUs: VUS,
      maxVUs: VUS,
      gracefulStop: '15s',
    },
  };
  thresholds = {
    'http_req_duration{endpoint:baseline-index}': ['p(95)<1000'],
    http_req_failed: ['rate<0.05'],
    baseline_get_success_rate: ['rate>0.95'],
    baseline_5xx_rate: ['rate<0.01'],
  };
} else {
  thresholds = {
    'http_req_duration{endpoint:sign}': ['p(95)<100'],
    'http_req_duration{endpoint:shorten}': ['p(95)<1000'],
    'http_req_duration{endpoint:redirect}': ['p(95)<100'],
    http_req_failed: ['rate<0.05'],
    end_to_end_success_rate: ['rate>0.90'],
    shorten_201_rate: ['rate>0.90'],
    redirect_ok_rate: ['rate>0.95'],
  };

  if (PAYMENT_ENABLED) {
    thresholds.sign_success_rate = ['rate>0.99'];
    thresholds.payment_settled_rate = ['rate>0.95'];
  }
  if (REDIRECT_PROBE_URL) {
    thresholds.independent_redirect_ok_rate = ['rate>0.95'];
  }

  const paymentScenario = LOAD_PROFILE === 'arrival-rate'
    ? {
        executor: 'constant-arrival-rate',
        exec: 'paymentFlow',
        rate: ARRIVAL_RATE,
        timeUnit: ARRIVAL_TIME_UNIT,
        duration: DURATION,
        preAllocatedVUs: VUS,
        // Each payment VU has one signer wallet. The profile is bounded rather
        // than spilling into unreviewed additional wallet/key slots.
        maxVUs: VUS,
        gracefulStop: '15s',
      }
    : {
        executor: 'constant-vus',
        exec: 'paymentFlow',
        vus: VUS,
        duration: DURATION,
        gracefulStop: '15s',
      };

  scenarios = { payment_flow: paymentScenario };
  if (REDIRECT_PROBE_URL) {
    scenarios.independent_redirects = {
      executor: 'constant-vus',
      exec: 'independentRedirectProbe',
      vus: 1,
      duration: DURATION,
      gracefulStop: '15s',
    };
  }
}

export const options = { scenarios, thresholds };

function validateConfiguration() {
  const normalisedBaseUrl = normaliseHttpUrl('BASE_URL', BASE_URL);
  const maxDuration = TRAFFIC_MODE === 'unpaid-baseline'
    ? MAX_BASELINE_DURATION_MS
    : MAX_RUN_DURATION_MS;
  parseDurationMs('DURATION', DURATION, maxDuration);
  parseDurationMs('PRECHECK_TIMEOUT', PRECHECK_TIMEOUT, 30000);
  parseDurationMs('ARRIVAL_TIME_UNIT', ARRIVAL_TIME_UNIT, 3600000);

  if (TRAFFIC_MODE !== 'paid' && TRAFFIC_MODE !== 'unpaid-baseline') {
    fail('TRAFFIC_MODE must be paid or unpaid-baseline');
  }
  if (LOAD_PROFILE !== 'closed-loop' && LOAD_PROFILE !== 'arrival-rate') {
    fail('LOAD_PROFILE must be closed-loop or arrival-rate');
  }
  if (TRAFFIC_MODE === 'unpaid-baseline') {
    if (PAYMENT_ENABLED) fail('PAYMENT_ENABLED must be false for unpaid-baseline traffic');
    if (normalisedBaseUrl !== DEV_BASELINE_URL) {
      fail(`BASE_URL must be ${DEV_BASELINE_URL} for unpaid-baseline traffic`);
    }
    if (LOAD_PROFILE !== 'arrival-rate') {
      fail('unpaid-baseline traffic requires LOAD_PROFILE=arrival-rate');
    }
    if (VUS !== 1) fail('unpaid-baseline traffic requires VUS=1');
    if (ARRIVAL_TIME_UNIT !== '1m') {
      fail('unpaid-baseline traffic requires ARRIVAL_TIME_UNIT=1m');
    }
    if (ARRIVAL_RATE > 60) fail('unpaid-baseline traffic allows at most 60 requests per minute');
    if (REDIRECT_PROBE_URL) fail('REDIRECT_PROBE_URL is not valid for unpaid-baseline traffic');
    return;
  }
  if (NETWORK_CAIP2 !== TESTNET_NETWORK) {
    fail(`NETWORK_CAIP2 must remain the owned testnet (${TESTNET_NETWORK})`);
  }
  if (!/^0x[a-fA-F0-9]{40}$/.test(SBC_CONTRACT)) {
    fail('SBC_CONTRACT_ADDRESS must be a 20-byte hexadecimal address');
  }
  if (REDIRECT_PROBE_URL) normaliseHttpUrl('REDIRECT_PROBE_URL', REDIRECT_PROBE_URL);

  if (!PAYMENT_ENABLED) return;

  normaliseHttpUrl('SIGNER_URL', SIGNER_URL);
  if (!/^0x[a-fA-F0-9]{40}$/.test(SERVICE_WALLET)) {
    fail('SERVICE_WALLET_ADDRESS is required when PAYMENT_ENABLED=true');
  }
}

function requireStatus(response, expectedStatus, message) {
  if (response.status !== expectedStatus) {
    fail(`${message} (status=${response.status})`);
  }
}

function responseHeader(response, name) {
  const expected = name.toLowerCase();
  const matchingName = Object.keys(response.headers).find(
    (headerName) => headerName.toLowerCase() === expected,
  );
  return matchingName ? response.headers[matchingName] : '';
}

function estimateRequiredWalletBalance() {
  const durationMs = parseDurationMs('DURATION', DURATION, MAX_RUN_DURATION_MS);
  let expectedPaymentsPerWallet;
  if (LOAD_PROFILE === 'arrival-rate') {
    const timeUnitMs = parseDurationMs('ARRIVAL_TIME_UNIT', ARRIVAL_TIME_UNIT, 3600000);
    const totalPayments = Math.ceil((durationMs / timeUnitMs) * ARRIVAL_RATE);
    expectedPaymentsPerWallet = Math.max(1, Math.ceil(totalPayments / VUS));
  } else {
    expectedPaymentsPerWallet = Math.max(1, Math.ceil(durationMs / (SLEEP_SECONDS * 1000)));
  }
  return (expectedPaymentsPerWallet + PAYMENT_BUFFER) * SBC_AMOUNT;
}

export function setup() {
  // Validate every input before the first HTTP request. This is the key guard
  // against an accidental bare k6 invocation reaching a testnet endpoint.
  validateConfiguration();

  const appUrl = normaliseHttpUrl('BASE_URL', BASE_URL);
  if (TRAFFIC_MODE === 'unpaid-baseline') return;
  requireStatus(
    http.get(`${appUrl}/livez`, { timeout: PRECHECK_TIMEOUT }),
    200,
    `BASE_URL liveness check failed for ${appUrl}/livez`,
  );
  requireStatus(
    http.get(`${appUrl}/ready`, { timeout: PRECHECK_TIMEOUT }),
    200,
    `BASE_URL readiness check failed for ${appUrl}/ready`,
  );

  if (!PAYMENT_ENABLED) return;

  // This does not settle or persist a URL. It verifies that the app is still
  // enforcing the x402 challenge before the signer begins paid iterations.
  const challenge = http.post(
    `${appUrl}/shorten`,
    JSON.stringify({ url: `https://example.invalid/resilience-gate/loadgen/precheck-${Date.now()}` }),
    {
      headers: { 'Content-Type': 'application/json' },
      timeout: PRECHECK_TIMEOUT,
      tags: { endpoint: 'shorten-precheck' },
    },
  );
  requireStatus(challenge, 402, 'Unsigned /shorten precheck did not return x402 challenge');
  if (!responseHeader(challenge, 'PAYMENT-REQUIRED')) {
    fail('Unsigned /shorten precheck omitted PAYMENT-REQUIRED');
  }

  const signerUrl = normaliseHttpUrl('SIGNER_URL', SIGNER_URL);
  requireStatus(
    http.get(`${signerUrl}/livez`, { timeout: PRECHECK_TIMEOUT }),
    200,
    `SIGNER_URL liveness check failed for ${signerUrl}/livez`,
  );
  const signerHealth = http.get(`${signerUrl}/health`, { timeout: PRECHECK_TIMEOUT });
  requireStatus(signerHealth, 200, `SIGNER_URL readiness check failed for ${signerUrl}/health`);

  let healthBody;
  try {
    healthBody = JSON.parse(signerHealth.body);
  } catch (_) {
    fail('SIGNER_URL /health returned invalid JSON');
  }
  if ((healthBody.wallet_count || 0) < VUS || (healthBody.wallets_bootstrapped || 0) < VUS) {
    fail(`Signer has insufficient bootstrapped wallets for VUS=${VUS}`);
  }

  const walletsResponse = http.get(`${signerUrl}/wallets`, { timeout: PRECHECK_TIMEOUT });
  requireStatus(
    walletsResponse,
    200,
    `SIGNER_URL wallet precheck failed for ${signerUrl}/wallets`,
  );
  let walletsBody;
  try {
    walletsBody = JSON.parse(walletsResponse.body);
  } catch (_) {
    fail('SIGNER_URL /wallets returned invalid JSON');
  }
  const wallets = Array.isArray(walletsBody.wallets) ? walletsBody.wallets : [];
  if (wallets.length < VUS) fail(`Signer returned ${wallets.length} wallets but VUS=${VUS}`);

  const requiredBalance = estimateRequiredWalletBalance();
  const selected = wallets
    .slice()
    .sort((left, right) => (left.wallet_index || 0) - (right.wallet_index || 0))
    .slice(0, VUS);
  for (const wallet of selected) {
    if (!wallet.bootstrapped || (wallet.permit2_allowance || 0) <= 0) {
      fail(`Signer wallet ${wallet.wallet_index} is not Permit2 bootstrapped`);
    }
    if ((wallet.sbc_balance || 0) < requiredBalance) {
      fail(`Signer wallet ${wallet.wallet_index} has insufficient SBC for this bounded run`);
    }
  }
}

export function baselineFlow() {
  const started = Date.now();
  const appUrl = normaliseHttpUrl('BASE_URL', BASE_URL);
  const response = http.get(`${appUrl}/`, {
    tags: { endpoint: 'baseline-index' },
    timeout: PRECHECK_TIMEOUT,
  });
  const succeeded = response.status === 200;
  check(response, { 'baseline GET / returns 200': (result) => result.status === 200 });
  baselineGetSuccessRate.add(succeeded);
  baseline5xxRate.add(response.status >= 500 && response.status < 600);
  baselineGetDuration.add(Date.now() - started);
}

function buildPaymentSignatureHeader(signerResponse) {
  const envelope = {
    x402Version: 2,
    accepted: {
      scheme: 'exact',
      network: NETWORK_CAIP2,
      amount: String(SBC_AMOUNT),
      asset: SBC_CONTRACT,
      payTo: SERVICE_WALLET,
      maxTimeoutSeconds: 300,
      extra: { assetTransferMethod: 'permit2' },
    },
    payload: {
      signature: signerResponse.signature,
      permit2Authorization: signerResponse.permit2Authorization,
    },
  };
  return encoding.b64encode(JSON.stringify(envelope));
}

function newDestinationUrl() {
  // `.invalid` is reserved and redirects are never followed. It keeps the
  // redirect leg independent without creating outbound internet traffic.
  return `https://example.invalid/resilience-gate/loadgen/${__VU}-${__ITER}-${Date.now()}`;
}

function redirectFromShorten(shortenResponse, appUrl) {
  let code = '';
  try {
    code = JSON.parse(shortenResponse.body).code || '';
  } catch (_) {
    return false;
  }
  if (!code) return false;

  const redirect = http.get(`${appUrl}/${encodeURIComponent(code)}`, {
    redirects: 0,
    tags: { endpoint: 'redirect' },
  });
  const succeeded = redirect.status === 302;
  check(redirect, { 'redirect 302': (response) => response.status === 302 });
  redirectOkRate.add(succeeded);
  return succeeded;
}

export function paymentFlow() {
  const started = Date.now();
  const appUrl = normaliseHttpUrl('BASE_URL', BASE_URL);
  let paymentSignature = null;

  if (PAYMENT_ENABLED) {
    const signerUrl = normaliseHttpUrl('SIGNER_URL', SIGNER_URL);
    const signResponse = http.post(
      `${signerUrl}/sign-permit2`,
      JSON.stringify({ wallet_index: __VU - 1, amount: SBC_AMOUNT }),
      {
        headers: { 'Content-Type': 'application/json' },
        timeout: PRECHECK_TIMEOUT,
        tags: { endpoint: 'sign' },
      },
    );
    if (signResponse.status !== 200) {
      signSuccessRate.add(false);
      paymentSettledRate.add(false);
      endToEndSuccessRate.add(false);
      endToEndDuration.add(Date.now() - started);
      return;
    }

    let signerBody;
    try {
      signerBody = JSON.parse(signResponse.body);
    } catch (_) {
      signSuccessRate.add(false);
      paymentSettledRate.add(false);
      endToEndSuccessRate.add(false);
      endToEndDuration.add(Date.now() - started);
      return;
    }
    if (!signerBody.signature || !signerBody.permit2Authorization) {
      signSuccessRate.add(false);
      paymentSettledRate.add(false);
      endToEndSuccessRate.add(false);
      endToEndDuration.add(Date.now() - started);
      return;
    }
    signSuccessRate.add(true);
    paymentSignature = buildPaymentSignatureHeader(signerBody);
  }

  const headers = { 'Content-Type': 'application/json' };
  if (paymentSignature) headers['PAYMENT-SIGNATURE'] = paymentSignature;
  const shorten = http.post(
    `${appUrl}/shorten`,
    JSON.stringify({ url: newDestinationUrl() }),
    { headers, tags: { endpoint: 'shorten' }, timeout: PRECHECK_TIMEOUT },
  );

  const created = shorten.status === 201;
  check(shorten, { 'shorten 201': (response) => response.status === 201 });
  shorten201Rate.add(created);
  shorten402Rate.add(shorten.status === 402);
  shorten409Rate.add(shorten.status === 409);
  shorten5xxRate.add(shorten.status >= 500 && shorten.status < 600);
  if (PAYMENT_ENABLED) {
    // The current application returns 201 only after settlement and
    // persistence; it intentionally does not expose a settlement hash/header.
    paymentSettledRate.add(created);
  }

  const redirected = created && redirectFromShorten(shorten, appUrl);
  endToEndSuccessRate.add(Boolean(created && redirected));
  // This fixed marker has no request, payment, endpoint, or wallet data. The
  // gate reads it only from this exact run-scoped Job before starting PodChaos.
  if (TRAFFIC_MODE === 'paid' && PAYMENT_ENABLED && created && redirected && !paidTrafficReadyReported) {
    console.log(PAID_TRAFFIC_READY_MARKER);
    paidTrafficReadyReported = true;
  }
  endToEndDuration.add(Date.now() - started);

  if (LOAD_PROFILE === 'closed-loop') sleep(SLEEP_SECONDS);
}

export function independentRedirectProbe() {
  if (!REDIRECT_PROBE_URL) return;
  const response = http.get(normaliseHttpUrl('REDIRECT_PROBE_URL', REDIRECT_PROBE_URL), {
    redirects: 0,
    tags: { endpoint: 'redirect' },
  });
  const succeeded = response.status === 302;
  check(response, { 'independent redirect 302': (result) => result.status === 302 });
  independentRedirectOkRate.add(succeeded);
  sleep(SLEEP_SECONDS);
}

function safeMetricSummary(metric) {
  const values = {};
  const rawValues = metric && metric.values && typeof metric.values === 'object' ? metric.values : {};
  for (const [name, value] of Object.entries(rawValues)) {
    if (typeof value === 'number' && Number.isFinite(value)) values[name] = value;
  }
  const thresholds = {};
  const rawThresholds = metric && metric.thresholds && typeof metric.thresholds === 'object'
    ? metric.thresholds
    : {};
  for (const [name, result] of Object.entries(rawThresholds)) {
    if (result && typeof result.ok === 'boolean') thresholds[name] = { ok: result.ok };
  }
  return {
    type: metric && typeof metric.type === 'string' ? metric.type : 'unknown',
    values,
    thresholds,
  };
}

// Completed Kubernetes containers cannot be used as a kubectl cp source.
// k6 calls handleSummary at the end of each test, so emit one deliberately
// sanitized, machine-readable marker that the runner can recover from logs.
// Do not serialize options, environment, request bodies, headers, or tags:
// they can carry endpoint or payment context that does not belong in evidence.
export function handleSummary(data) {
  const metrics = {};
  const rawMetrics = data && typeof data.metrics === 'object' ? data.metrics : {};
  for (const name of Object.keys(rawMetrics).sort()) {
    metrics[name] = safeMetricSummary(rawMetrics[name]);
  }
  const summary = {
    schema_version: 'resilience-gate.loadgen-summary/v1',
    traffic_mode: TRAFFIC_MODE,
    metrics,
  };
  const serialized = JSON.stringify(summary);
  return {
    '/results/summary.json': serialized,
    stdout: `${SUMMARY_MARKER}${serialized}\n`,
  };
}

// Preserve the ordinary k6 entrypoint for local reviewers while the CronJob
// uses the named paymentFlow scenario above.
export default function () {
  if (TRAFFIC_MODE === 'unpaid-baseline') {
    baselineFlow();
    return;
  }
  paymentFlow();
}
