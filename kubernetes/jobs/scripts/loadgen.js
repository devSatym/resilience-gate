import http from 'k6/http';
import encoding from 'k6/encoding';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

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

const thresholds = {
  'http_req_duration{endpoint:sign}': ['p(95)<100'],
  'http_req_duration{endpoint:shorten}': ['p(95)<1000'],
  'http_req_duration{endpoint:redirect}': ['p(95)<100'],
  http_req_failed: ['rate<0.05'],
  shorten_201_rate: ['rate>0.90'],
  redirect_ok_rate: ['rate>0.95'],
};

if (PAYMENT_ENABLED) {
  thresholds.sign_success_rate = ['rate>0.99'];
  thresholds.payment_settled_rate = ['rate>0.95'];
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

export const options = { scenarios: { payment_flow: paymentScenario }, thresholds };

function validateConfiguration() {
  normaliseHttpUrl('BASE_URL', BASE_URL);
  parseDurationMs('DURATION', DURATION, MAX_RUN_DURATION_MS);
  parseDurationMs('PRECHECK_TIMEOUT', PRECHECK_TIMEOUT, 30000);
  parseDurationMs('ARRIVAL_TIME_UNIT', ARRIVAL_TIME_UNIT, 3600000);

  if (LOAD_PROFILE !== 'closed-loop' && LOAD_PROFILE !== 'arrival-rate') {
    fail('LOAD_PROFILE must be closed-loop or arrival-rate');
  }
  if (NETWORK_CAIP2 !== TESTNET_NETWORK) {
    fail(`NETWORK_CAIP2 must remain the owned testnet (${TESTNET_NETWORK})`);
  }
  if (!/^0x[a-fA-F0-9]{40}$/.test(SBC_CONTRACT)) {
    fail('SBC_CONTRACT_ADDRESS must be a 20-byte hexadecimal address');
  }
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
      return;
    }

    let signerBody;
    try {
      signerBody = JSON.parse(signResponse.body);
    } catch (_) {
      signSuccessRate.add(false);
      paymentSettledRate.add(false);
      return;
    }
    if (!signerBody.signature || !signerBody.permit2Authorization) {
      signSuccessRate.add(false);
      paymentSettledRate.add(false);
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

  if (created) redirectFromShorten(shorten, appUrl);

  if (LOAD_PROFILE === 'closed-loop') sleep(SLEEP_SECONDS);
}

// Preserve the ordinary k6 entrypoint for local reviewers while the CronJob
// uses the named paymentFlow scenario above.
export default function () {
  paymentFlow();
}
