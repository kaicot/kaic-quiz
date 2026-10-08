"""Read a public Google Form page: the quiz title, its questions and all five options in order.

The page embeds the form as ``FB_PUBLIC_LOAD_DATA_``. Google does not document that structure,
so everything here is defensive: any surprise becomes an ``Err`` and the user can still load a
문항표 made by the AI instead. Answers are not on the public page; they come from the responses.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from quiz_reporter.errors import Err, ErrorInfo, Ok, Result
from quiz_reporter.quiz.bank import normalize

_URL = re.compile(
    r"https://docs\.google\.com/forms/(?:u/\d+/)?d/(?:e/)?[A-Za-z0-9_-]+/(?:viewform|edit)?[^\s]*"
)
_DATA = re.compile(r"FB_PUBLIC_LOAD_DATA_\s*=\s*(.*?);\s*</script>", re.S)
_MAX_BYTES = 5 * 1024 * 1024
TIMEOUT_SECONDS = 10.0
_CHOICE_TYPES = frozenset({2, 3, 4})  # multiple choice, dropdown, checkboxes


@dataclass(frozen=True, slots=True)
class FormQuestion:
    title: str
    options: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FormPage:
    title: str
    questions: tuple[FormQuestion, ...]


def _error(reason: str) -> Err:
    return Err(
        (
            ErrorInfo(
                "QUIZ_FORM_UNREADABLE",
                "error.quiz_form_unreadable",
                None,
                context={"reason": reason},
            ),
        )
    )


def valid_form_url(text: str) -> str | None:
    match = _URL.match(text.strip())
    if match is None:
        return None
    url = match.group(0)
    # Always read the respondent view; never an edit page that needs a login.
    base = url.split("?", 1)[0]
    base = re.sub(r"/(viewform|edit)$", "", base.rstrip("/"))
    return f"{base}/viewform"


def parse_form_page(html: str) -> Result[FormPage]:
    match = _DATA.search(html)
    if match is None:
        return _error("폼 내용을 찾지 못했습니다. 응답을 받는 공개 폼 주소인지 확인하세요.")
    try:
        data: Any = json.loads(match.group(1))
        form = data[1]
        title = normalize(str(data[3] if len(data) > 3 and data[3] else form[8] or ""))
        questions: list[FormQuestion] = []
        for item in form[1] or []:
            kind = item[3]
            entries = item[4] or []
            if kind not in _CHOICE_TYPES or not entries:
                continue
            options = tuple(normalize(str(option[0])) for option in (entries[0][1] or []))
            questions.append(FormQuestion(normalize(str(item[1] or "")), options))
    except (ValueError, TypeError, IndexError, KeyError):
        return _error("폼 내용의 형식이 예상과 다릅니다. 문항표를 AI로 만들어 불러오세요.")
    if not questions:
        return _error("폼에서 객관식 문항을 찾지 못했습니다.")
    return Ok(FormPage(title, tuple(questions)))


Fetcher = Callable[[str], bytes]


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Quiz Reporter)"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        return response.read(_MAX_BYTES + 1)


def fetch_form_page(address: str, fetch: Fetcher = _fetch) -> Result[FormPage]:
    url = valid_form_url(address)
    if url is None:
        return _error(
            "구글 폼 주소가 아닙니다. 'https://docs.google.com/forms/…' 주소를 붙여 넣으세요."
        )
    try:
        data = fetch(url)
    except (urllib.error.URLError, OSError, ValueError):
        return _error("폼을 열 수 없습니다. 인터넷 연결과 폼 주소(공개 여부)를 확인하세요.")
    if len(data) > _MAX_BYTES:
        return _error("폼 페이지가 너무 큽니다.")
    return parse_form_page(data.decode("utf-8", "replace"))


__all__ = ["FormPage", "FormQuestion", "fetch_form_page", "parse_form_page", "valid_form_url"]
