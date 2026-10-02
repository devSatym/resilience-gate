# Payment contract: x402 v2 with Permit2

**Status:** implemented contract with a bounded owned-testnet smoke. The
recorded sequence observed `402 → signed 201 → redirect 302 → replay 409` and
retained a sanitized receipt. This remains narrower than an audited settlement,
custody, or production-payment claim.

## Scope and ownership

`POST /shorten` is the chargeable operation. A client proves authority to pay
with an x402 v2 `PAYMENT-SIGNATURE` header; the application asks a configured
facilitator to verify and settle that authorization. The application does not
hold payer keys or submit chain transactions directly.

The server owns the price and payment requirements. A client may echo selected
terms, but cannot lower an amount, replace an asset, change a recipient, or
extend a timeout by changing its header. Addresses, network, asset, amount,
and facilitator URL are deployment configuration, not source-code constants in
this contract.

Amounts are decimal strings in the asset's smallest unit. They are never
floating-point values.

## HTTP exchange

### 1. Challenge

When payment is required and a valid payment header is absent, the server
returns `402 Payment Required`. Its `PAYMENT-REQUIRED` header is standard
base64-encoded JSON. The response body may repeat the descriptor for clients
that cannot read response headers.

```json
{
  "x402Version": 2,
  "error": "PAYMENT-SIGNATURE header is required",
  "resource": {
    "url": "https://service.example/shorten",
    "description": "Create a shortened URL",
    "mimeType": "application/json"
  },
  "accepts": [
    {
      "scheme": "exact",
      "network": "eip155:<chain-id>",
      "amount": "<atomic-unit-amount>",
      "asset": "<token-address>",
      "payTo": "<merchant-address>",
      "maxTimeoutSeconds": 300,
      "extra": { "assetTransferMethod": "permit2" }
    }
  ]
}
```

The server emits the descriptor from its own `PaymentRequirements` object. A
client-provided descriptor is never treated as the source of truth.

### 2. Payment submission

The client selects one offered requirement, obtains a signature from its
signer, and sends another standard-base64 JSON object in
`PAYMENT-SIGNATURE`:

```json
{
  "x402Version": 2,
  "accepted": {
    "scheme": "exact",
    "network": "eip155:<chain-id>",
    "amount": "<atomic-unit-amount>",
    "asset": "<token-address>",
    "payTo": "<merchant-address>",
    "maxTimeoutSeconds": 300,
    "extra": { "assetTransferMethod": "permit2" }
  },
  "payload": {
    "signature": "0x<65-byte-ECDSA-signature>",
    "permit2Authorization": {
      "permitted": { "token": "<token-address>", "amount": "<amount>" },
      "from": "<payer-address>",
      "spender": "<x402-Permit2-proxy-address>",
      "nonce": "<uint256>",
      "deadline": "<unix-seconds>",
      "witness": { "to": "<merchant-address>", "validAfter": "<unix-seconds>" }
    }
  }
}
```

The application strictly decodes the header to a JSON object and sends it only
alongside server-owned requirements. It never derives price, asset, recipient,
network, or timeout from client input. The configured facilitator is the
authority that verifies the signed payload and its accepted terms; malformed
headers and rejected signatures are payment failures, not URL creations.

### 3. Facilitator calls

After local validation, the application sends the normalized signed payload to
the configured facilitator. Both calls use the same payload and the same
server-owned requirements:

```json
{
  "x402Version": 2,
  "paymentPayload": { "...": "normalized signed payload" },
  "paymentRequirements": { "...": "server-owned exact/permit2 terms" }
}
```

The application calls `/verify` before `/settle`.

- A valid verification response has `isValid: true`.
- A verification response with `isValid: false` is invalid even if its HTTP
  status is successful. Its human-readable reason is for logs, not a metrics
  label or control-flow enum.
- A successful settlement response has `success: true` and a canonical
  transaction identifier. The application validates that identifier before it
  is persisted or returned.
- HTTP success with a malformed body is a facilitator failure. It must never
  be treated as settlement success.

The application returns `201 Created` only after a successful settlement and
successful persistence of the new short URL. Its current response is the URL
creation payload; settlement identifiers remain in the audit record rather
than being echoed to clients. Missing, malformed, expired, or rejected
authorizations receive `402`; a client can request a fresh challenge before
retrying. A timeout, transport error, or malformed facilitator response is an
availability failure (`5xx`), not evidence that the payer declined to pay.

An existing destination URL is not a new chargeable creation: the intended
contract returns its existing short URL without settling a second payment.

## Permit2 signer contract

The signer is the private-key boundary. It exposes a narrow endpoint such as
`POST /sign-permit2` and returns only `signature` plus
`permit2Authorization`; callers never receive a private key.

The authorization is an EIP-712 `PermitWitnessTransferFrom` signature using a
Permit2 domain with:

- `name: "Permit2"`;
- the configured chain ID;
- the configured Permit2 verifying contract; and
- no `version` field.

The signed message binds the token, amount, Permit2/x402 proxy spender, random
uint256 nonce, expiry, and witness recipient. The proxy address is the
spender—not the facilitator—and the witness binds funds to the configured
merchant address. Signatures must use an Ethereum-compatible `v` value
(`27` or `28`).

Permit2 uses unordered bitmap nonces, so the signer can generate a
cryptographically random nonce without a per-request RPC nonce lookup. Before
signing payments, each payer wallet needs an ERC-20 allowance for Permit2. The
signer may perform that allowance check and any approval bootstrap at startup;
it must not turn a request-time signing failure into a hidden payment attempt.

## Replay, persistence, and consistency limits

Replay prevention has three complementary layers:

1. Permit2 consumes the signed nonce on successful on-chain settlement.
2. A facilitator can return an idempotent prior result for a duplicate signed
   payload instead of issuing another transaction.
3. The application stores `settlement_tx_hash` under a unique constraint and
   records the payer and settlement time where available.

The third layer is important even when the first two work: an idempotent
facilitator reply can otherwise make a duplicate request look like a new
application-level creation. A duplicate settlement identifier must not create
a second short URL.

There is no distributed transaction spanning facilitator settlement and the
application database. The safe ordering is settle first, then persist. If the
database write fails after settlement, a payer may have a settled transaction
without a URL response. Recovery must reconcile by the validated settlement
identifier and must not silently settle again. This is an explicit operational
limit, not a condition to hide behind a generic success response.

## Failure and observability contract

Payment metrics use stable, coarse outcomes such as `required`, `settled`,
`signature_invalid`, `verify_rejected`, `settle_rejected`,
`invalid_response`, and `facilitator_unavailable`. Raw facilitator messages
are log context only because they are not a stable API vocabulary.

The application records total end-to-end settlement duration and separate
facilitator `verify` and `settle` durations. The signer records signing and
approval-bootstrap outcomes independently. These signals distinguish an invalid
client authorization from a signer, application, facilitator, or dependency
failure during a resilience test.

## Evidence boundary

Unit tests prove codec behavior, term comparison, response validation, and
signature recovery with deterministic fixtures. The final paid smoke added a
sanitized live record bound to source, rendered, application, signer,
gate-runner, and load-generator identity while omitting sensitive payment data.
It proves that bounded invocation only; every later testnet execution still
needs its own record.
