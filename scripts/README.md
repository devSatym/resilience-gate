# Scripts

## test-payment-flow.sh
Manual, opt-in x402 v2 / Permit2 smoke utility. It never runs in CI because a
successful run settles one real **testnet** payment. It checks:

- Step 1: `POST /shorten` without `PAYMENT-SIGNATURE` → `402` plus `PAYMENT-REQUIRED`
- Step 2: `POST /sign-permit2`, then submit the encoded authorization → `201`
- Step 3: reuse that authorization with another URL → `409` settlement replay guard

Use an owned, funded testnet wallet only. The script refuses to run until its
explicit authorization variable is set:

```bash
RUN_TESTNET_PAYMENTS=1 \
BASE_URL=http://localhost:8000 \
SIGNER_URL=http://localhost:8080 \
./scripts/test-payment-flow.sh
```

See `docs/runbooks/testnet-payments.md` for Compose setup, wallet boundaries,
and failure interpretation. A successful smoke run is operational evidence for
that invocation only; it is not chaos-gate or release evidence.

---

## fund-test-wallet.sh

Address-only faucet utility. Drips SBC to a wallet address on Radius testnet, then verifies
the on-chain balance with `cast call`. **No private key required** — unsigned flow only.
If the faucet re-enables `signature_required`, the script stops and prints the web faucet URL.

Prerequisites: `curl`, `jq`, `cast` (Foundry), `bc`

Usage:
```bash
# Fund the SERVICE_WALLET from the staging secret
SERVICE_WALLET=$(kubectl get secret url-shortener-secrets -n url-shortener-staging \
  -o jsonpath='{.data.SERVICE_WALLET_ADDRESS}' | base64 -d)
./scripts/fund-test-wallet.sh "$SERVICE_WALLET"

# Custom faucet endpoint
FAUCET_URL=https://testnet.radiustech.xyz/api/v1/faucet ./scripts/fund-test-wallet.sh 0x...
```

Expected output:
- `Drip response: {"success":true,"tx_hash":"0x..."}` — faucet confirmed
- `SBC balance: 0.500000 SBC` — on-chain ground truth via `cast call balanceOf`

Error cases:
- `signature_required` — exits with web faucet URL; script does not hold SERVICE_WALLET key
- `rate_limited` — exits with retry_after_ms; wait and retry (60 req/60s limit per address)

---

## fund-loadgen-wallets.sh

Convenience wrapper for the three signer/loadgen wallets. Derives the wallet addresses from
`WALLET_KEY_1..3` using `cast wallet address`, then calls `fund-test-wallet.sh` for each.

Usage:
```bash
WALLET_KEY_1=... WALLET_KEY_2=... WALLET_KEY_3=... \
  ./scripts/fund-loadgen-wallets.sh
```

Notes:
- accepts keys with or without `0x`
- skips unset wallet env vars
- use `SLEEP_BETWEEN_S=...` if you want a longer pause between faucet calls

---

## loadgen.js

k6 load generator for continuous payment traffic. Designed to run as a Kubernetes Job
inside `url-shortener-staging` so it's subject to the same Chaos Mesh network experiments
as the app.

**Signer-backed flow**: each VU asks the internal `radius-signer` service to submit a
real SBC ERC-20 transfer from its assigned funded wallet, then uses the resulting
confirmed `tx_hash` as payment.

Per-VU iteration:
1. `POST radius-signer /pay` → get confirmed `tx_hash`
2. `POST /shorten` with `tx_hash` → expect 201
3. `GET /{code}` with `redirects: 0` → expect 302

Pre-run behavior:
1. Verify app, RPC, and signer health
2. Fetch signer wallet balances from `GET /wallets`
3. Fail fast if any active VU wallet is under the required starting SBC balance for the planned run
4. Retry `/shorten` briefly when the app reports a transient receipt-visibility lag for a freshly confirmed `tx_hash`

Custom metrics tracked:
| Metric | Description |
|--------|-------------|
| `tx_submit_success_rate` | Rate of successful on-chain transaction submission |
| `tx_receipt_success_rate` | Rate of successful transaction confirmation receipt fetches |
| `tx_confirmation_ms` | End-to-end time from submit to confirmed receipt |
| `shorten_201_rate` | Rate of 201 on /shorten |
| `shorten_402_rate` | Rate of 402 on /shorten |
| `shorten_409_rate` | Rate of 409 (replay — should be 0) |
| `shorten_5xx_rate` | Rate of 5xx responses on /shorten |
| `redirect_ok_rate` | Rate of 302 on /{code} |

Current thresholds:
- `http_req_duration p(95) < 500ms`
- `http_req_failed rate < 0.05`
- `shorten_201_rate rate > 0.95`
- `redirect_ok_rate rate > 0.95`
- `tx_submit_success_rate rate > 0.95` when `PAYMENT_ENABLED=true`
- `tx_receipt_success_rate rate > 0.95` when `PAYMENT_ENABLED=true`

Canonical k6 job scripts now live under `kubernetes/jobs/scripts/`.

Run locally with k6:
```bash
SERVICE_WALLET=$(kubectl get secret url-shortener-staging-secret -n url-shortener-staging \
  -o jsonpath='{.data.SERVICE_WALLET_ADDRESS}' | base64 -d)

BASE_URL=http://localhost:8000 \
SIGNER_URL=http://localhost:8080 \
RPC_URL=https://rpc.testnet.radiustech.xyz \
SERVICE_WALLET_ADDRESS="$SERVICE_WALLET" \
VUS=3 DURATION=1m \
k6 run kubernetes/jobs/scripts/loadgen.js
```

Run as a one-off k8s Job from the suspended CronJob template (Phase 5+):
```bash
# Apply the kustomize package once (signer + secrets + CronJob template + script ConfigMap).
# Idempotent — the CronJob is suspended, so applying it never auto-fires a load run.
kubectl apply -k kubernetes/jobs

# Trigger a load run on demand (each invocation creates a uniquely-named Job):
RUN=loadgen-$(date +%s)
kubectl -n url-shortener-staging create job --from=cronjob/loadgen "$RUN"
kubectl -n url-shortener-staging logs -f "job/$RUN"
```

ArgoCD / Kustomize notes:
- `kubernetes/jobs/kustomization.yaml` is the source ArgoCD should point at.
- `kubernetes/jobs/scripts/loadgen.js` is the canonical script source.
- Kustomize generates the `ConfigMap` from that file automatically.
- `radius-signer` is deployed from the same Kustomize package and reuses `loadgen-wallet-secret`.
- Update the `images:` section in `kustomization.yaml` to an immutable `sha-<short>` tag or digest for `radius-signer`.
