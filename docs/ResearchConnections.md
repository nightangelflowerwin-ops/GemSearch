# Research workspace

Research adds a conversation area to the desktop workspace. Financial data provides direct Financial Datasets queries independently of the model. Both run requests in background workers so the scanner and navigation remain responsive.

## MiroThinker connection

Open Research, then Connections. Enter the base URL and served model name of your running model endpoint. The upstream deployment example uses `http://127.0.0.1:61002/v1` and the served name `mirothinker`. Remote endpoints must use HTTPS. An optional model key is stored locally using Windows credential protection. Save and test checks that the configured model is advertised by the endpoint.

The server must support OpenAI-compatible chat completions and structured function calls. MiroThinker's upstream LobeChat integration documents its vLLM tool parser and chat template. Configure those on the model server; raw tool markup is rejected rather than displayed as an answer.

This integration provides a bounded research loop around the connected model, Financial Datasets queries and optional read-only GemSearch tools. It does not install model weights, start an inference server or reproduce the full MiroFlow benchmark, browser, code-execution or multimodal framework. The default loop permits up to 12 model turns, 24 tool requests and four minutes. Stop cancels subsequent work immediately; an already transmitted request may finish at its provider. Network calls have bounded timeouts.

Local GemSearch data access is off by default. Enable it in Connections only if you want the connected model to read token, wallet, alert and scanner status records. Private credentials and strategy settings are excluded from those tools. Conversation history is stored locally; prior conversation messages are sent to the configured model when you ask another question. New chat clears that history. Model reasoning is not shown or saved as conversation text.

## Financial Datasets

Account registration and API-key creation are free. Current published market-data access starts with a $20 credit purchase for 1,000 requests. Personal and commercial licenses differ; shipping the connector does not grant data redistribution rights. The application does not purchase credits, enable automatic reload or share an account key with other users.

The crypto ticker directory is available without a key. Prices, historical prices, financial statements, company news and SEC filings require a key and appropriate account access. Enter the key in Research > Connections. The environment variable `FINANCIAL_DATASETS_API_KEY` is also supported. Each requested dataset may consume provider credits. No automatic financial-data polling is added.

Financial data supports annual, quarterly and trailing twelve-month statements. Historical queries use daily intervals and explicit date ranges. The MCP tool also supports weekly, monthly and yearly intervals. Requests encode and validate their parameters, bound response size, and report access failures without treating missing data as zero. Results identify their provider and fetch time; provider market data does not replace independent blockchain verification in the token scanner.

Use Copy financial MCP connection in Connections to attach these queries to another MCP-compatible assistant. The same executable starts in `--financial-mcp` mode and exposes `financial_query`, which selects the requested dataset. Keys remain in local protected storage rather than in the copied configuration. The existing GemSearch MCP connection remains available separately.

## Source investigation

The REA workflow routes complete source repositories to direct source inspection. These observations are based on source and live endpoint checks, rather than decompilation or claimed production-model execution.

| Project | Inspected commit | Observed interface |
| --- | --- | --- |
| MiroMindAI/MiroThinker | `1c4253f6774bf40314271a827304b842100e054c` | OpenAI-compatible model serving, custom tool parser, iterative tool use, separate MiroFlow framework |
| financial-datasets/mcp-server | `08e7a3dbb949d3d99bbd6d6f3a22e5f02973ec58` | MIT-licensed stdio MCP wrapper around Financial Datasets REST endpoints |

The Financial Datasets source exposes eleven tools, including two aliases for the same historical crypto route. GemSearch covers those underlying datasets through one validated query tool. Current stock intervals and news limits follow the published API specification rather than older source comments. The vendor also provides a hosted MCP endpoint whose tool names differ from the older repository.

Sources: [MiroThinker source](https://github.com/MiroMindAI/MiroThinker), [model integration guide](https://github.com/MiroMindAI/MiroThinker/blob/1c4253f6774bf40314271a827304b842100e054c/apps/lobehub-compatibility/README.md), [Financial Datasets source](https://github.com/financial-datasets/mcp-server/blob/08e7a3dbb949d3d99bbd6d6f3a22e5f02973ec58/server.py), [API specification](https://www.financialdatasets.ai/openapi.json), [pricing](https://www.financialdatasets.ai/pricing), [registration](https://www.financialdatasets.ai/register).
