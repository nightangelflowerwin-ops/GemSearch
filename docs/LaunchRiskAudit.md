# GemSearch launch risk audit

Reviewed October 8, 2026. Scope: the tracked GemSearch desktop app, browser extension and local web backend. This is a source review of the six risks in the supplied post, not a certification of legal compliance or an audit of external providers, deployed portfolios or historical binaries.

| Risk | Current implementation | Required action if the product changes |
| --- | --- | --- |
| Children and signup | No GemSearch signup or hosted account service found. COPPA applicability depends on child-directed services or actual knowledge of collecting personal information from children under 13, not simply absence of an age question. | Assess audience and data collection before adding accounts or child-directed features. An age gate alone is not COPPA compliance. |
| Remote fonts | Desktop uses Segoe UI from the operating system. Web and extension assets do not load Google Fonts. | Keep fonts local and retain their distribution licences when adding font files. |
| Session replay | No session replay SDK found. The extension collects rendered posts after activation; that collection still needs clear disclosure. | Review privacy, recording and consent requirements before introducing replay or analytics. Input masking alone does not settle those requirements. |
| Marketing email | No marketing email sender found. Telegram alerts are a separate feature. | Before commercial email campaigns, supply a valid postal address, a functioning opt-out and the other CAN-SPAM requirements. A documentation link alone does not implement unsubscribe processing. |
| Subscription renewal | No subscription checkout or recurring GemSearch billing found. | Before subscriptions, implement prominent renewal disclosures, affirmative consent, confirmation, notices where required and straightforward cancellation. |
| User uploads and copyright | Imports and research records are local. The optional live launch integration can publish metadata to Pinata/IPFS; external publication requires rights to the content. No GemSearch-operated public user-content hosting service was found. | Assess DMCA applicability before operating a hosting or information-location service. Agent designation is only one safe-harbor condition. Do not claim registration or safe harbor without completing the applicable process. |

## Changes made

Expanded the privacy documentation to cover desktop storage, provider requests, IP exposure, wallet data, optional Telegram delivery, third-party browser links and connected assistants. No artificial signup or billing flow was added to the existing product.

## Limits of the supplied penalty claims

Maximum penalties and statutory damages are not automatic bills for each visitor, child or session. The relevant law, covered conduct, jurisdiction, evidence and available remedies matter. COPPA penalties are described by the FTC per violation. Copyright statutory damages up to $150,000 concern qualifying willful infringement per work, not an automatic fee for every uploaded image. Failure to designate a DMCA agent does not itself establish infringement.

## Primary references

- [FTC COPPA guidance](https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions)
- [FTC CAN-SPAM guidance](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business)
- [California automatic renewal guidance](https://oag.ca.gov/node/608083)
- [Copyright Office DMCA directory and registration](https://copyright.gov/dmca-directory/)
- [Copyright Office safe-harbor requirements](https://copyright.gov/512/)
- [Copyright statutory damages guidance](https://www.copyright.gov/help/faq/faq-fairuse.html)
