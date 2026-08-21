# Staging load testing

This runbook creates an explicitly requested, bounded load run against the
owned Radius testnet staging environment. It is not part of the ordinary test
suite or pull-request validation: each successful `POST /shorten` can settle
testnet tokens.

Do not point this tooling at a production network. The load script rejects a
network other than `eip155:72344`, and the in-cluster CronJob is scoped to
`url-shortener-staging`.

## Before a run

Confirm all of the following with the environment owner:

- the current Kubernetes context is the intended owned staging cluster;
- the `url-shortener-staging` application release and `radius-signer`
  deployment are healthy;
- `resilience-gate-signer` and `resilience-gate-loadgen` ExternalSecrets are
  `Ready`;
- signer wallets are funded only for the bounded testnet budget and have
  completed their Permit2 bootstrap; and
- the selected duration is at most ten minutes and virtual users at most three.

The signer is the private-key boundary. Its ExternalSecret contains the payer
keys; the load-generator ExternalSecret contains only `SERVICE_WALLET_ADDRESS`.
Never add wallet keys to the Job, a shell environment, logs, artifacts, or Git.

## Review a no-network plan

The default command is a local plan: it does not call `kubectl`, Kubernetes,
the signer, the application, a facilitator, or a testnet endpoint.

```bash
./scripts/run-loadgen.sh --plan \
  --profile arrival-rate \
  --duration 10m \
  --vus 3 \
  --arrival-rate 60 \
  --arrival-time-unit 1m
```

Use `closed-loop` for a fixed number of virtual users with a pause between
iterations:

```bash
./scripts/run-loadgen.sh --plan \
  --profile closed-loop \
  --duration 5m \
  --vus 2 \
  --sleep-seconds 2
```

The plan validates profiles and bounds locally. It intentionally cannot create
a Job; that requires the separate `--execute` acknowledgement.

## Execute one reviewed run

After reviewing the plan and current context, execute the same configuration:

```bash
./scripts/run-loadgen.sh --execute \
  --profile arrival-rate \
  --duration 10m \
  --vus 3 \
  --arrival-rate 60 \
  --arrival-time-unit 1m
```

The runner first verifies that the source CronJob remains suspended, waits for
the app, signer, and both ExternalSecrets, then creates a uniquely named Job
from the CronJob template. It does not unsuspend or modify the CronJob. The
template is digest-pinned and disables k6's anonymous usage report. Its setup
checks `/livez` and `/ready` on the app, then `/livez`, `/health`, and
`/wallets` on the signer before it begins paid iterations.

The default profile creates unique URLs whose destination uses
`example.invalid`; redirect checks use `redirects: 0`, so the client never
follows the destination off-cluster. A separate `REDIRECT_PROBE_URL` can be
added to a reviewed one-off Job only when an independently pre-existing short
URL must be measured.

## Results and evidence limits

The Job writes k6's summary to `/results/summary.json` and remains for 24 hours
after completion. The runner copies it to
`/tmp/resilience-gate-loadgen/<job>-summary.json` by default. Use
`--artifact-dir /absolute/path` to choose another local location.

Record the source revision, rendered signer and k6 image digests, namespace,
Job name, profile, duration, VUs, metrics summary, and any relevant logs. A
single manual load run is operational evidence only; it is not a release
promotion, chaos-gate pass, or proof of a production payment system.

If the Job fails before or during a run, keep the summary/logs, stop creating
new Jobs, and investigate the failed layer (precheck, signer, app, facilitator,
or persistence) before retrying. Do not broaden VU counts, duration, wallet
funding, or network scope to work around a failure.
