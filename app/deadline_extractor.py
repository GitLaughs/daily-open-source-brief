from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Iterable


EVENT_KEYWORDS = {
    "报名": "报名",
    "申报": "申报",
    "考试": "考试",
    "答辩": "答辩",
    "确认": "确认",
    "讲座": "讲座",
    "截止": "截止",
}

FULL_DATE_PATTERNS = [
    re.compile(r"(?P<event>报名|申报|考试|答辩|确认|讲座|选课确认).{0,6}?截止[：:]?\s*(?P<y>20\d{2})[年./-](?P<m>\d{1,2})[月./-](?P<d>\d{1,2})"),
    re.compile(r"(?P<event>报名截止|截止时间|考试时间|答辩时间|确认时间|申报截止)[：:]?\s*(?P<y>20\d{2})[年./-](?P<m>\d{1,2})[月./-](?P<d>\d{1,2})"),
    re.compile(r"(?P<y>20\d{2})[年./-](?P<m>\d{1,2})[月./-](?P<d>\d{1,2})日?.{0,12}?(?P<event>截止|报名|申报|考试|答辩|确认|讲座)"),
]
MONTH_DAY_PATTERNS = [
    re.compile(r"(?P<event>报名截止|截止时间|考试时间|答辩时间|确认时间|申报截止)[：:]?\s*(?P<m>\d{1,2})月(?P<d>\d{1,2})日?"),
    re.compile(r"(?P<m>\d{1,2})月(?P<d>\d{1,2})日?.{0,12}?(?P<event>截止|报名|申报|考试|答辩|确认|讲座)"),
]


@dataclass(frozen=True)
class DeadlineCandidate:
    title: str
    deadline: date
    event_type: str
    confidence: float
    source_url: str = ""
    item_id: int | None = None
    status: str = "pending"

    def as_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "deadline": self.deadline.isoformat(),
            "event_type": self.event_type,
            "confidence": self.confidence,
            "source_url": self.source_url,
            "status": self.status,
        }


def extract_deadlines(
    title: str,
    snippet: str,
    detail_text: str | None = None,
    *,
    source_url: str = "",
    item_id: int | None = None,
    today: date | None = None,
) -> list[DeadlineCandidate]:
    today = today or date.today()
    fields = [
        ("title", title or "", 0.9),
        ("snippet", snippet or "", 0.7),
        ("detail", detail_text or "", 0.65),
    ]
    candidates: list[DeadlineCandidate] = []
    seen: set[tuple[str, date]] = set()
    for _field_name, text, base_confidence in fields:
        for deadline, event_type, has_year in _scan_text(text, today.year):
            confidence = base_confidence if has_year else min(base_confidence, 0.5)
            status = "expired" if deadline < today else "pending"
            if status == "expired":
                confidence = min(confidence, 0.1)
            key = (event_type, deadline)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                DeadlineCandidate(
                    title=title,
                    deadline=deadline,
                    event_type=event_type,
                    confidence=round(confidence, 2),
                    source_url=source_url,
                    item_id=item_id,
                    status=status,
                )
            )
    candidates.sort(key=lambda item: (item.status != "pending", item.deadline, -item.confidence))
    return candidates


def _scan_text(text: str, default_year: int) -> Iterable[tuple[date, str, bool]]:
    normalized = re.sub(r"\s+", " ", text)
    for pattern in FULL_DATE_PATTERNS:
        for match in pattern.finditer(normalized):
            parsed = _make_date(match.group("y"), match.group("m"), match.group("d"))
            if parsed:
                yield parsed, normalize_event_type(match.group("event")), True
    for pattern in MONTH_DAY_PATTERNS:
        for match in pattern.finditer(normalized):
            parsed = _make_date(str(default_year), match.group("m"), match.group("d"))
            if parsed:
                yield parsed, normalize_event_type(match.group("event")), False


def _make_date(year: str, month: str, day: str) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def normalize_event_type(text: str) -> str:
    for keyword, event_type in EVENT_KEYWORDS.items():
        if keyword in text:
            return event_type
    return "事项"
