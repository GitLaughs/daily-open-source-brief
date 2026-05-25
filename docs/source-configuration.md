# Source Configuration

Sources are configured in `config/sources.yml`.

## GitHub

GitHub queries use the standard GitHub search syntax. `{pushed_after}` is replaced with a rolling date before collection.

```yaml
github:
  queries:
    - name: ai-active
      q: "topic:ai stars:>3000 pushed:>{pushed_after} archived:false fork:false"
      limit: 20
```

## RSS

RSS and Atom feeds should use public feed URLs.

```yaml
rss:
  - name: example-feed
    title: Example Feed
    url: https://example.com/feed.xml
    source_type: tech_news
    enabled: true
```

## Public Webpages

Webpage collectors parse simple list pages containing links and dates. Use this only for public pages you are allowed to fetch.

```yaml
webpages:
  - name: example-notices
    title: Example Notices
    url: https://example.edu/notices/
    source_type: public_notice
    enabled: false
    url_allow_patterns:
      - /notice/
```

Keep private portals, authenticated pages, and personal dashboards out of committed config.
