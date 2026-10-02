# x402 and Permit2 design status

**Status: implemented source contract with one bounded owned-testnet
observation.** A direct interaction observed `402 → signed 201 → replay 409`.
No separately versioned payment-evidence bundle is retained, so this note must
not be read as proof of audited settlement, wallet funding, custody, or an
on-chain transaction finality claim.

## Intended request path

When payment configuration is enabled, a client requests `POST /shorten` with
a destination URL:

1. Without `PAYMENT-SIGNATURE`, the application returns `402` and supplies a
   server-generated x402 v2 `PAYMENT-REQUIRED` descriptor.
2. The client obtains a Permit2 authorization from the isolated signer and
   supplies it in the base64-encoded payment header.
3. The application decodes the header, combines it with its own configured
   payment requirements, then calls the configured facilitator's `/verify`
   endpoint before `/settle`.
4. Only a validated settlement response with a transaction hash can precede a
   new URL record. The persistence layer uses the settlement transaction
   identifier for replay detection.

The application owns its payment terms: network, asset, amount, recipient,
timeout, and facilitator endpoint are deployment configuration, not fields a
client may choose by changing the request header. Existing URL destinations are
returned without another chargeable creation attempt.

## Private-key boundary

`signer/main.py` defines a separate FastAPI service for Permit2
authorizations. It exposes `POST /sign-permit2`, returning a signature and its
authorization payload rather than a key. It performs the configured Permit2
allowance bootstrap before declaring its wallet set ready; request-time signing
uses a random Permit2 nonce and local EIP-712 signing.

This is an isolation design, not a custody claim. The signer still depends on
correct secret injection, configured RPC behavior during bootstrap, wallet
funding, and facilitator/network compatibility in a real lab.

## Failure behavior represented in source

| Condition | Intended application outcome |
| --- | --- |
| Missing payment header | `402 Payment Required` with server-owned requirements. |
| Malformed header or rejected authorization | Payment rejection; no URL is created. |
| Facilitator transport failure or invalid response | Availability failure rather than a fabricated settlement. |
| Successful settlement followed by duplicate transaction identity | Replay protection rejects a second use. |
| Database failure after settlement | Availability failure requiring deliberate reconciliation; there is no distributed transaction. |
| Signer not bootstrapped or requested wallet unavailable | Signer returns a non-ready/error response; callers must not treat it as a valid authorization. |

The last two rows are important operational limits. They are deliberately not
hidden behind a generic success response. The bounded testnet observation above
does not exercise every facilitator or chain failure mode and is not a durable
settlement-evidence record.

## Scope and verification boundary

The Helm values restrict the intended environments to configured testnet
settings. This repository does not claim mainnet support, a real merchant
integration, wallet custody controls beyond the described process boundary, or
production payment availability.

Offline tests can validate codecs, requirements comparison, response handling,
and signing behavior with fixtures. A verified payment claim still requires a
separately sanitized, retained record that identifies the source revision,
immutable workload and signer identities, configuration scope, and actual
settlement result. The recorded interaction does not satisfy that higher bar.
