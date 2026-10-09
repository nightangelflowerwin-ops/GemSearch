# Wallet directory

Open Wallet directory to search saved KOL names, handles, addresses, tags and coin labels. Find KOL performs a public profile lookup. Refresh selected checks the selected address again. Results are saved locally and remain searchable offline.

Each wallet can have several identity claims. The directory preserves their profile names, X handles, platforms, wallet attribution evidence and source snapshot dates. Hover over Identity evidence to see the attribution details. Shared addresses and conflicting names retain separate claims. An EVM identity address is kept as an EVM address; it is not assigned to Ethereum or another network without evidence.

Source attributed means the provider returned a wallet link with an attribution category. It does not mean GemSearch independently proved that someone controls the wallet. Address validation is separate from ownership verification. The saved count measures unique network-family and address pairs, not independent verified people or the provider's advertised profile count.

Edit tags stores personal wallet labels separately from source records. Tag coin stores a token network, contract address and personal label alongside a wallet. These links are research notes, not proof that a KOL owns, bought, sold or endorsed a coin. Refreshing a profile preserves personal labels and coin links. A successful empty result retires that lookup's prior source claims; a failed request keeps the existing data.

While monitoring is active, saved profile lookups become eligible for refresh after 24 hours. The app checks one due query per 15 seconds. Requests are serialized and provider permission or rate-limit errors pause provider access for at least an hour. Stopping monitoring pauses automatic refresh. The directory view reloads locally once a minute.

Import list accepts CSV or JSON up to 20 MB and 100,000 identity claims. Existing name/address Solana lists still work. Flattened records can contain name, address, chain (`solana` or `evm`), handle, x_handle, platform, proof and tags. Tags can be a JSON list or a comma-separated CSV field. JSON can also contain public profile responses with accounts and wallets, or an object containing a profiles list. Invalid files are rejected before writes. Importing the same records again does not duplicate wallets.

The public profile search is not a full-directory export. A 5,000-wallet capacity test does not establish a 5,000-wallet verified dataset. Complete bulk coverage needs a usable bulk source. Profile data and personal tags are not bundled into public downloads or published to GitHub. The connector code is included so each installation can build its own local directory.

Solana wallet tracking remains available through Track selected wallet. EVM identities are available for tagging; EVM wallet transaction tracking and KOL trade analysis are separate features.
