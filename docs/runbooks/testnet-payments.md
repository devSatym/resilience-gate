# Testnet Permit2 payment smoke runbook

Use this runbook only with an owned Radius testnet environment. The smoke
utility intentionally causes one settlement after its preflight challenge, so
it is excluded from ordinary unit tests and pull-request validation.

## Preconditions

- Docker with Compose, `curl`, `jq`, and `base64`
- an available Radius testnet RPC endpoint and facilitator
- a merchant/service wallet address
- one funded payer wallet reserved for this testnet environment

The payer key belongs only in a local ignored `signer/.env` file or a secret
manager. Do not paste it into shell history, Git, an issue, or a test result.
The signer owns the private key boundary: its `POST /sign-permit2` response
contains a signed authorization, never a key.

## Prepare the opt-in local stack

Copy the reviewed example, then fill the empty merchant and wallet values with
testnet-only material:

```bash
cp signer/.env.example signer/.env
# edit signer/.env locally; it is ignored by Git
```

Start the normal local API dependencies plus the opt-in payment overlay:

```bash
docker compose --env-file signer/.env \
  -f docker-compose.yml \
  -f docker-compose.payments.yml \
  --profile payments up --build
```

The signer's startup checks the configured chain, reads each wallet's SBC
balance and Permit2 allowance, and—only if needed—submits the one-time
`SBC.approve(Permit2, MAX_UINT256)` bootstrap transaction. A successful boot
does not make request-time signing depend on RPC; `/sign-permit2` signs a local
Permit2 EIP-712 payload with a random bitmap nonce.

In another terminal, wait for the local app and signer to become ready:

```bash
curl --fail http://localhost:8000/ready
curl --fail http://localhost:8080/health | jq .
curl --fail http://localhost:8080/wallets | jq .
```

If signer health is non-200, inspect the configuration, RPC reachability,
chain ID, wallet funding, and approval bootstrap state before proceeding. Do
not bypass signer readiness by copying a key into another component.

## Execute one smoke run

The explicit environment variable acknowledges that this call can settle test
tokens. Use a unique destination URL if rerunning:

```bash
RUN_TESTNET_PAYMENTS=1 \
BASE_URL=http://localhost:8000 \
SIGNER_URL=http://localhost:8080 \
./scripts/test-payment-flow.sh
```

The expected sequence is:

1. A new unsigned `POST /shorten` returns `402` with `PAYMENT-REQUIRED`.
2. The script asks the signer for a Permit2 authorization matching the offered
   amount, then sends an x402 v2 `PAYMENT-SIGNATURE` header and expects `201`.
3. It reuses that authorization against a different URL and expects `409`,
   proving the application-level settlement identifier guard saw the duplicate
   facilitator result.

`402` at the first step is success for this smoke. A `402` at the signed step
usually means the chosen wallet has insufficient balance or allowance, the
signature terms differ from the server-owned challenge, or the authorization
expired. A `503` indicates an unavailable dependency, not a payment rejection.

## Cleanup and evidence limits

Stop the local containers when done:

```bash
docker compose --env-file signer/.env \
  -f docker-compose.yml \
  -f docker-compose.payments.yml \
  --profile payments down --volumes
```

Record the date, source revision, image identity, environment, and observed
HTTP statuses if this run contributes to an operations log. Do not call a
single manual smoke run release verification or chaos evidence; the later
chaos-gate procedure owns those claims.
