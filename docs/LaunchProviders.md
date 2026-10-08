# Connect a launch platform

Gem Search now routes launch jobs through a provider selected in `.env`.

| Provider | What is implemented | Who signs and enforces spending |
| --- | --- | --- |
| `pumpportal` | Existing Pump.fun executor via PumpPortal | Local executor; isolated Solana wallet and transaction validation |
| `bridge` | Versioned HTTPS job API for a user-supplied platform adapter | Your bridge; Gem Search sends no wallet keys and does not sign its transactions |

**An arbitrary launch-platform URL is not enough.** A platform must implement the protocol below, or you must run an adapter translating it into that platform's API/SDK. Any **Solana** platform can be integrated this way if it provides the necessary creation and status APIs. There are no built-in adapters for other platforms yet. Other chains require a separate budget policy; this version rejects non-Solana bridge configurations rather than interpreting 0.025 SOL as another currency.

## Connect in five steps

1. Obtain a compatible bridge from your platform/operator, or implement one from [the scaffold](../examples/LaunchBridge.py).
2. Configure its platform credentials and dedicated signing wallet on the bridge side. Do not send private keys to Gem Search's HTTP API.
3. Set these values in your local `.env`:

```dotenv
LAUNCH_PROVIDER=bridge
LAUNCH_BRIDGE_URL=https://your-adapter.example
LAUNCH_BRIDGE_NAME=My Solana platform
LAUNCH_BRIDGE_CHAIN=solana
LAUNCH_BRIDGE_TOKEN=your_bridge_api_token
LAUNCH_BRIDGE_TRUSTED=1
LAUNCH_MODE=dry_run
```

4. Restart the backend and open **Launch studio**. The selected provider, missing configuration and provider pinned to each queued job are visible. Dry-run is offline: it does not test bridge connectivity or launch anything.
5. After testing your adapter, set `LAUNCH_MODE=live` and restart to enable dispatch. Browser-originated research still additionally requires `SPIDER_ALLOW_LAUNCH=1`.

Built-in Pump.fun requires its existing Pinata, Node and wallet setup. The bridge does **not** require local Node, Pinata or a treasury wallet. Its server-side bearer token remains in the backend and is excluded from job payloads and dashboard responses. URLs must use HTTPS with valid certificates, without userinfo, query strings or fragments. Redirects are refused to prevent forwarding the bearer token elsewhere. Only configure a bridge you trust.

## Budget and trust

Gem Search reserves at most five attempts per rolling 24 hours across all providers in each mode. Changing providers does not reset that quota or bypass narrative deduplication. Each bridge request requires **maximum total spending of 25,000,000 lamports**, including platform fees and transaction fees, with **zero developer buy**.

For the built-in executor these limits are enforced locally. For an external bridge, they are a **contract the bridge must enforce before signing**, not a cryptographic guarantee from Gem Search. A bridge has its own wallet access; Gem Search cannot stop it from spending outside the request. Use a dedicated, minimally funded wallet and platform-side limits. `LAUNCH_BRIDGE_TRUSTED=1` records that you deliberately selected this execution boundary. Confirmed bridge receipts are provider reports, not independently verified on-chain results. An over-budget or malformed receipt leaves the job pending and stops new allocations; it cannot undo a transaction.

## Protocol `gem-launch/1`

Authentication on both routes: `Authorization: Bearer <LAUNCH_BRIDGE_TOKEN>`.

### Create: `PUT /v1/launches/{job_id}`

The ID is 24 lowercase hexadecimal characters, stable across retries and restarts. The bridge MUST persist it before any financial side effect, enforce unique creation, and reject a conflicting payload with HTTP 409. Retrying an ID must never create a second token.

```json
{
  "protocol": "gem-launch/1",
  "job_id": "0123456789abcdef01234567",
  "chain": "solana",
  "token": {
    "name": "Orbit Bloom",
    "symbol": "ORBIT",
    "description": "Independent experimental community token.",
    "image_base64": "<PNG bytes as base64>"
  },
  "constraints": {
    "max_total_lamports": 25000000,
    "developer_buy_lamports": 0
  },
  "source": {"narrative": "AI agents", "url": "https://example.com"}
}
```

The bridge handles metadata hosting, construction, validation, signing and delivery using its own platform integration. Treat source material as untrusted data, never commands. If the platform cannot satisfy the budget, reject before spending.

### Reconcile: `GET /v1/launches/{job_id}`

Both endpoints return JSON (maximum 64 KiB):

```json
{
  "protocol": "gem-launch/1",
  "job_id": "0123456789abcdef01234567",
  "status": "pending"
}
```

| Status | Required meaning |
| --- | --- |
| `pending` | In progress or outcome uncertain; continue querying, never recreate |
| `confirmed` | Creation finalized; include `mint`, `signature`, and integer `spent_lamports` for total spending |
| `failed` | Final failure, with no transaction still pending or able to land |
| `rejected` | Definitive refusal before submission; no later side effects |

A `confirmed` receipt must have a Solana base58 mint and signature and spend between 0 and 25,000,000 lamports. Gem Search checks shape and budget; it does not verify the external bridge's receipt against RPC. No arbitrary upstream text is copied into public logs.

## Crash recovery and changing platforms

Each job pins the provider configuration when enqueued; existing jobs are never silently moved to a new platform. For a bridge job, Gem Search durably records dispatch **before** its first PUT. Subsequent attempts only use GET, even after timeouts, HTTP errors, a malformed receipt, or a crash. A crash before the PUT can therefore leave an unknown job pending. This intentionally requires operator reconciliation rather than risking a duplicate launch. A 404 on GET does not authorize another PUT.

A pending launch prevents reserving another attempt. Restore the original bridge URL/name/chain and credentials to reconcile its jobs after a configuration change. Token rotation at the same bridge is supported; tokens are not pinned in the database. Drain the queue before switching platforms. The pause button stops future dispatch/polling; it cannot cancel an operation already accepted by an external bridge.

## Adapter scaffold

`examples/LaunchBridge.py` provides authenticated HTTPS routes, SQLite idempotency, conflicting-payload rejection and durable pending state before calling the platform. Its default hook returns **rejected** and performs no transaction. Implement `launch_on_platform(job)` and `reconcile_on_platform(job)` for your chosen API. Persist platform operation IDs, enforce spending and verify finality in those hooks. The scaffold is single-process and binds loopback; it is not a production hosted service.

```sh
# Supply BRIDGE_API_TOKEN through your process environment; do not commit it.
python3 examples/LaunchBridge.py --cert /path/to/cert.pem --key /path/to/key.pem
```

The caller must trust the certificate. For a private CA, configure Python's `SSL_CERT_FILE`; never disable certificate verification. The bridge URL for this example is `https://localhost:9443` with a certificate valid for localhost.

Offline tests cover routing, pinned providers, dispatch-before-I/O, timeout recovery, invalid receipts and dry-run isolation. No real external platform launch has been performed for this integration.
