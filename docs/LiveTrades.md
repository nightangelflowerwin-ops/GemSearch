# Live trades

Start monitoring and open Live trades to see decoded Solana swaps. Automatic selection follows up to five Meteora DAMM v2 pools from the scanner, giving watched tokens priority. Choose a token to prioritize its supported pool and filter the trade list. Tokens on other protocols continue to use the existing market scanner.

The stream subscribes to confirmed pool activity through Solana RPC. Each notification is queued on disk. The app fetches the transaction, matches the swap instruction to its event, and reads the trader, direction, amounts, pool price and reserves. Failed transactions are excluded. Repeated notifications do not duplicate trades. Recovery checks missed signatures and resumes interrupted pagination.

The table shows the last 100 collected trades. Double-click a trade to open its transaction explorer. Confirmed trades can change. The app rechecks them at finalized commitment before including them in a complete five-minute flow total.

Pool price is quoted in SOL or USDC. USD trade values require a fresh SOL market reference captured when the trade is collected. USDC trade values remain unpriced in USD rather than assuming a peg. Historical trades without a contemporaneous reference do not contribute to a claimed USD total.

Five-minute flow uses finalized buys minus sells, measured in USD. It needs continuous stream coverage for five minutes and 45 seconds, a cleared recovery queue, finalized transactions and valid USD references for every trade in the window. The measured window ends 45 seconds behind current activity. Incomplete totals stay unavailable. This measures trade flow through the selected pool, not total capital entering a token across every pool or venue.

Market cap and the scanner's headline USD prices still come from the market feed. A swap price alone does not establish circulating supply or independently verify market cap. Wallet balance tracking remains separate from decoded pool trades. Bot classification, additional swap protocols and EVM streaming are not included in this first version.

Monitoring continues when the window is minimized. Stop pauses collection. Existing queued transactions remain on disk for recovery when monitoring resumes. Public RPC capacity and transaction availability can delay results; this is not a guarantee of exchange-level latency or complete global coverage.

Protocol format: [Meteora DAMM v2 SDK](https://github.com/MeteoraAg/damm-v2-sdk). Subscription behavior: [Solana logsSubscribe](https://solana.com/docs/rpc/websocket/logssubscribe).
