# What Gem Search reads and where it goes

The extension reads rendered post text, the post permalink/timestamp, and external anchors inside viewport X tweet articles after you activate it. The selected feed remains in scope when you switch tabs or use another application. It doesn't use cookies, network interception, account-action APIs, DMs, passwords or browser history. Message/account/settings/compose routes are excluded.

Choose **Until I stop it** or a time limit before starting. Optional auto-scroll can move the selected feed while it is in the background; it avoids scrolling while you edit the visible page. Stop scanner in the popup works from any tab. Overlay Stop, dismiss, disconnect, reaching the deadline, closing the selected tab, leaving supported feed routes/origin, or restarting the browser ends the session. Worker suspension and switching tabs do not end it. Only the selected tab is scanned. Stop ends future collection; queued items may still be forwarded. Disconnect & clear local queue removes pairing and pending items, but does not erase records already received by the backend.

Visible does **not** necessarily mean public: your account might be able to see protected posts. Only activate collection where you intend to use the visible material. The extension does not infer or bypass access restrictions.

| Data | Location / destination |
| --- | --- |
| Pending post captures | chrome.storage.local, maximum 200 pending items |
| Pairing token | Trusted extension contexts; not passed to content scripts |
| Scanner session, selected tab/origin and optional deadline | Trusted chrome.storage.local; renderer receives its session ID and settings, not the pairing token |
| Captured posts, research evidence and decisions | SQLite in local data/ |
| Public linked pages | Fetched by the local crawler; target sites see an HTTP request from your computer |
| Grok review excerpts | Sent to api.x.ai only when GROK_ENABLED=1 with your local key |
| xAI API key | Local .env/environment; not the extension or a hosted Gem Search service |
| Optional token metadata | Sent to Pinata and public IPFS only by the explicitly enabled live launch module |

No Gem Search telemetry or hosted collection endpoint is implemented. The local backend does not remove your browser or provider's own telemetry. Review xAI/Pinata terms for their retention and billing policies if you enable those services.

Processed raw browser captures older than seven days are purged during subsequent ingestion; evidence excerpts already attached to project dossiers can remain until you remove your local database. Pending extension items stay until acknowledged or until you use Disconnect & clear local queue. Turning off Grok stops future model calls but does not recall data already sent to a provider.

Stop the server before deleting local research data. If using the optional launch module, preserve transaction state and wallet backups rather than deleting the whole data directory. Never share that directory in a public issue or repository.

## Windows desktop app

The desktop app stores token records, watched addresses, wallet tracking history, alerts and settings locally in `%LOCALAPPDATA%/GemSearch` by default. It has no GemSearch signup or subscription checkout. No session replay, keystroke recording SDK, marketing email sender or remote font loader is implemented. Interface fonts come from the operating system.

Starting monitoring sends requested token and wallet addresses to market and blockchain providers. Dexscreener supplies market quotes and discovery lists. Solana RPC and PublicNode RPC endpoints receive blockchain queries, including addresses and transaction identifiers. These providers can see your network IP and requested data. Blockchain wallet addresses can be linked to people; tracking them is not anonymous merely because the transactions are public.

Live trades subscribes to selected public pool addresses over a Solana RPC WebSocket while monitoring is active. Transaction signatures, decoded trade history and recovery cursors are stored locally. USD references use the existing market provider. Stopping monitoring closes the stream and pauses processing; saved history remains on disk.

Wallet directory lookups send the entered handle or address to the public identity search provider. Saved lookups may be refreshed while monitoring is active. The provider can see these requests and your IP address. Identity claims, aliases, personal tags and coin labels are stored locally. The app does not reproduce the provider website's analytics beacon or send wallet copy and outbound-click events. Imported lists are read locally and are not uploaded by the import action.

Solscan and Cielo receive requests when their integrations are used. Explorer and account buttons open third-party websites in your browser, where their own privacy policies apply. Optional Telegram notifications send configured alert content to Telegram. The desktop app does not upload its local database to a GemSearch-hosted service.

The local MCP connection exposes supported records to an assistant you connect. That assistant or its provider may process the returned data under its own policies. Do not connect assistants you do not trust with these records.

Stopping monitoring stops new scheduled collection. It does not delete stored history or recall requests already sent. Close the app before removing local data, and keep credentials, databases and wallet information out of public bug reports.
