# Importing from another collector

The dashboard accepts a JSON array or `{"posts": [...]}`. Each scan supports 1–1,000 posts, at most 30 distinct project URLs and 2 MB total input.

```json
{
  "posts": [
    {
      "id": "collector-specific-id",
      "author": "researcher",
      "text": "A public project release with technical documentation",
      "project_url": "https://example.com/project",
      "project_name": "Example project",
      "followers": 240,
      "created_at": "2026-10-05T12:00:00Z"
    }
  ]
}
```

`project_name` and `followers` are optional. Timestamps require a timezone. Source data is not independently authenticated by the import endpoint. Audience counts are rough context, never proof of identity or organic growth.

For background import, run `python3 app.py --autopilot`. Write a file to data/inbox with a temporary extension, then rename it to `.json`. Successful inputs move to data/processed. Never put wallet/key files in the inbox.

Browser captures use a separate, stricter shape (`url`, `text`, `created_at`, `links`) and must include a valid X post permalink. The extension does not need to know a project URL to contribute to narrative grouping.
