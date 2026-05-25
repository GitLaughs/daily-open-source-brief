from __future__ import annotations

import argparse
import os
from pathlib import Path

from .ccswitch import configure_from_ccswitch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rotate daily brief LLM provider from cc-switch balance")
    parser.add_argument("--env-out", default="/opt/daily-open-source-brief/.llm.env")
    parser.add_argument("--force-fallback", action="store_true")
    return parser.parse_args()


def shell_escape(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def main() -> int:
    args = parse_args()
    provider = configure_from_ccswitch(force_fallback=args.force_fallback)
    if not provider:
        print("LLM_FROM_CCSWITCH disabled")
        return 0

    out = Path(args.env_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"OPENAI_API_KEY={shell_escape(os.environ['OPENAI_API_KEY'])}",
        f"OPENAI_BASE_URL={shell_escape(os.environ['OPENAI_BASE_URL'])}",
        f"OPENAI_MODEL={shell_escape(os.environ['OPENAI_MODEL'])}",
        f"DAILY_BRIEF_LLM_PROVIDER={shell_escape(provider['name'])}",
        f"DAILY_BRIEF_LLM_PROVIDER_KIND={shell_escape(provider.get('kind') or 'db')}",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out.chmod(0o600)
    print(
        "selected provider={name} kind={kind} model={model} remaining={remaining}".format(
            name=provider["name"],
            kind=provider.get("kind") or "db",
            model=provider["model"],
            remaining=provider.get("remaining"),
        )
    )
    if provider.get("fallback_reason"):
        print("fallback reason=" + provider["fallback_reason"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
