from __future__ import annotations

import argparse
from datetime import date

from .runner import RunOptions, run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate daily open-source brief")
    parser.add_argument("--date", dest="digest_date", default=date.today().isoformat())
    parser.add_argument("--config", default=None)
    parser.add_argument("--plugins-config", default=None, help="Plugin config file, defaults to config/plugins.yml")
    parser.add_argument("--skip-mail", action="store_true")
    parser.add_argument("--skip-lark", action="store_true")
    parser.add_argument("--force-send", action="store_true")
    parser.add_argument("--sample", action="store_true", help="Use bundled sample repositories and skip GitHub API")
    parser.add_argument("--skip-web", action="store_true", help="Skip configured public webpage sources")
    parser.add_argument("--skip-rss", action="store_true", help="Skip configured RSS/Atom sources")
    parser.add_argument("--archive-retention-days", type=int, default=None, help="Delete archive HTML files older than this many days")
    parser.add_argument("--collect-only", action="store_true", help="Fetch, rank, and store candidates without sending")
    parser.add_argument("--send-only", action="store_true", help="Build and deliver a digest from stored candidates")
    parser.add_argument("--delivery-slot", default=None, help="Delivery slot key, defaults to YYYY-MM-DD-HH")
    parser.add_argument("--lark-only-important", action="store_true", help="Send only high-score items to Lark")
    return parser.parse_args()


def main() -> int:
    return run(RunOptions.from_namespace(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
