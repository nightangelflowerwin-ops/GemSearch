# Local trust boundaries

- The Python engine binds only to loopback. It is not a public multi-user service.
- The extension is activated per tab. Host permissions permit only the local engine; activeTab permits the current X page. No cookies, browsing history or DM APIs are used.
- The pairing token grants only capture/status access. It cannot invoke launch controls. It is stored in extension trusted contexts; content scripts do not receive it.
- `.env`, SQLite, captured posts, API keys, launch state and wallet keypairs are excluded from Git and extension archives. Never publish your `data/` directory.
- Grok sees bounded excerpts only when explicitly enabled. Retrieved text is untrusted, and the model has no tools, execution rights, wallet access or launch API. Its output is schema-checked and citations must reference supplied evidence IDs.
- The crawler validates DNS answers and pins the socket to a public address, including after redirects. This does not make retrieved content truthful.
- Experimental token creation is separate, disabled by default, and browser captures cannot trigger it unless SPIDER_ALLOW_LAUNCH=1. See docs/AUTOLAUNCH.md.

To revoke an extension pairing, stop the engine, remove `data/extension-key`, restart, then reconnect with the new code. To stop financial work use Pause queue and stop the engine; already broadcast transactions cannot be cancelled.

Report security issues privately through the repository owner's GitHub contact or GitHub Security Advisories if enabled. Do not include real keys, private feed captures or signed live transactions in a public issue.


## External launch bridges

Bridge mode moves signing and spending enforcement to the configured operator. Gem Search sends only token metadata, source context, a stable job ID and constraints over authenticated HTTPS; no local wallet key is sent. A bearer token authorizes launches at that bridge, so keep it secret. Only a compatible, trusted Solana adapter should be configured. The 0.025 SOL constraint is enforced by that adapter, not locally guaranteed. Receipts are not independently checked against chain state. Unknown outcomes remain pending and block new allocations. See [the protocol](docs/LaunchProviders.md).
