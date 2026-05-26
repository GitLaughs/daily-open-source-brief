from __future__ import annotations

from typing import Any

import requests

from .config import env_bool


def trust_env_proxy() -> bool:
    return env_bool("DAILY_BRIEF_TRUST_ENV_PROXY", False)


def http_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = trust_env_proxy()
    return session


def http_get(url: str, **kwargs: Any) -> requests.Response:
    with http_session() as session:
        return session.get(url, **kwargs)
