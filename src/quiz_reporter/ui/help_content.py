"""The in-app user manual: sections, the HTML of the whole manual and its style sheet.

Qt rich text understands a subset of HTML and CSS, so boxes and numbered steps are tables and the
look comes from class selectors in the document's default style sheet. There is one light theme,
so the colors below are a small fixed palette.

Two helpers mark button labels. ``_btn`` is for buttons that live on the 퀴즈 채점 page; a test
checks each of them against the real page so this manual cannot drift from the screen. ``_ui``
is for labels on other screens.
"""

from __future__ import annotations

from html import escape
from typing import NamedTuple

import quiz_reporter
from quiz_reporter.quiz.bank import (
    BANK_HEADERS,
    BANK_SHEET,
    READABLE_LIMIT,
    TRAP_TYPES,
)
from quiz_reporter.quiz.grading import SITTING_GAP

TEXT = "#1F2933"
MUTED = "#52606D"
ACCENT = "#0F766E"
ACCENT_SOFT = "#E6F4F1"
WARN_BACKGROUND = "#FFF7E6"
WARN_TEXT = "#8A4B00"
BORDER = "#D9E2EC"


class HelpSection(NamedTuple):
    key: str
    title: str


HOMEPAGE = "https://github.com/kaicot/kaic-quiz"

SECTIONS: tuple[HelpSection, ...] = (
    HelpSection("home", "처음 화면(홈)"),
    HelpSection("new_quiz", "새 퀴즈 채점"),
    HelpSection("question_bank", "문항표와 AI 프롬프트"),
    HelpSection("reports", "리포트 읽는 법"),
    HelpSection("quiz_list", "퀴즈 목록"),
    HelpSection("settings", "설정"),
    HelpSection("files", "폴더와 업데이트"),
    HelpSection("trouble", "문제 해결"),
    HelpSection("about", "프로그램 정보"),
)

# The help section that matches each main-window page.
PAGE_SECTIONS: dict[str, str] = {
    "home": "home",
    "new_quiz": "new_quiz",
    "quiz_list": "quiz_list",
    "settings": "settings",
}

HELP_STYLESHEET = f"""
    body {{ font-family: "Malgun Gothic", "Segoe UI", sans-serif; color: {TEXT}; font-size: 14px; }}
    a {{ color: {ACCENT}; font-weight: 700; text-decoration: underline; }}
    h1 {{ font-size: 24px; color: {TEXT}; margin-bottom: 4px; }}
    h2 {{ font-size: 20px; color: {ACCENT}; margin-top: 28px; margin-bottom: 6px; }}
    h2 a {{ color: {ACCENT}; text-decoration: none; }}
    h3 {{ font-size: 15px; color: {TEXT}; margin-top: 16px; margin-bottom: 4px; }}
    p {{ margin-top: 4px; margin-bottom: 6px; }}
    li {{ margin-bottom: 3px; }}
    .lead {{ color: {MUTED}; }}
    .muted {{ color: {MUTED}; font-size: 12px; }}
    .ui {{ font-weight: 700; }}
    .btn {{ font-weight: 700; color: {ACCENT}; }}
    table.grid {{ border-collapse: collapse; border-color: {BORDER}; margin-top: 4px;
        margin-bottom: 8px; }}
    table.grid th {{ background-color: {ACCENT_SOFT}; font-weight: 700; }}
    td.step {{ background-color: {ACCENT_SOFT}; font-weight: 700; }}
    td.tip {{ background-color: {ACCENT_SOFT}; border-left: 4px solid {ACCENT}; }}
    td.warn {{ background-color: {WARN_BACKGROUND}; color: {WARN_TEXT};
        border-left: 4px solid {WARN_TEXT}; }}
    pre {{ font-family: Consolas, "Malgun Gothic", monospace; font-size: 13px; }}
"""

_EXAMPLE_FILE = "001_20260001_가나.pdf"


def _ui(label: str) -> str:
    """A label on some other screen, as the screen shows it."""
    return f"<span class='ui'>[{escape(label)}]</span>"


def _btn(label: str) -> str:
    """A button of the 퀴즈 채점 page; tests compare it with the real page."""
    return f"<span class='btn'>[{escape(label)}]</span>"


def _name(label: str) -> str:
    """A name or heading shown on screen that is not a button."""
    return f"<span class='ui'>{escape(label)}</span>"


def _grid(headers: tuple[str, ...], rows: tuple[tuple[str, ...], ...], widths: str = "") -> str:
    head = "".join(f"<th align='left'>{cell}</th>" for cell in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    width = f" width='{widths}'" if widths else ""
    return (
        f"<table class='grid' border='1' cellspacing='0' cellpadding='6'{width}>"
        f"<tr>{head}</tr>{body}</table>"
    )


def _box(kind: str, title: str, text: str) -> str:
    return (
        "<table width='100%' cellspacing='0' cellpadding='10' style='margin-top:6px;"
        f"margin-bottom:8px'><tr><td class='{kind}'><b>{title}</b> {text}</td></tr></table>"
    )


def _tip(text: str) -> str:
    return _box("tip", "알아 두기", text)


def _warn(text: str) -> str:
    return _box("warn", "주의", text)


def _privacy(text: str) -> str:
    return _box("warn", "개인정보", text)


def _flow(steps: tuple[tuple[str, str], ...]) -> str:
    cells = []
    for index, (title, text) in enumerate(steps):
        if index:
            cells.append("<td align='center' valign='middle' width='24'><b>→</b></td>")
        cells.append(
            f"<td class='step' valign='top'>{title}<br><span class='muted'>{text}</span></td>"
        )
    return (
        "<table cellspacing='4' cellpadding='10' style='margin-top:6px;margin-bottom:8px'>"
        f"<tr>{''.join(cells)}</tr></table>"
    )


def _anchor(section: str) -> str:
    title = next(item.title for item in SECTIONS if item.key == section)
    return f"<h2><a name='{section}'>{title}</a></h2>"


def _steps(*items: str) -> str:
    return "<ol>" + "".join(f"<li>{item}</li>" for item in items) + "</ol>"


def _bullets(*items: str) -> str:
    return "<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>"


def _home() -> str:
    return (
        _anchor("home") + "<p>퀴즈 리포터는 구글 폼으로 본 5지선다 퀴즈의 응답을 채점하고, 학생마다"
        " '왜 틀렸는지' 알려 주는 PDF 리포트를 만드는 프로그램입니다.</p>"
        + _flow(
            (
                ("① 응답 파일", "구글 폼에서<br>CSV를 내려받음"),
                ("② 문항표", "AI가 만든 해설과<br>오답 이유 (선택)"),
                ("③ 채점", "버튼 한 번으로<br>채점과 리포트"),
                ("④ 리포트", "인쇄용 PDF와<br>학생별 PDF"),
            )
        )
        + "<h3>위쪽 메뉴</h3>"
        + _grid(
            ("메뉴", "하는 일"),
            (
                (_name("홈"), "새 퀴즈를 채점하거나 최근 퀴즈의 리포트를 엽니다."),
                (_name("퀴즈 목록"), "지난 퀴즈를 모두 보고, 다시 열고, 다시 만들고, 지웁니다."),
                (_name("설정"), "저장 위치 확인, 새 버전 안내, 이전 자료 가져오기."),
                (_name("?"), "이 도움말을 엽니다. 키보드 F1 키로도 열립니다."),
            ),
        )
        + "<h3>홈 화면</h3>"
        + _bullets(
            f"큰 {_ui('＋ 새 퀴즈 채점')} 버튼으로 채점을 시작합니다.",
            "그 아래 카드에 최근 퀴즈가 나옵니다. 카드에는 퀴즈 이름, 날짜, 인원, 평균 점수가"
            f" 있고 {_ui('리포트')} 버튼으로 그 퀴즈의 리포트를 바로 엽니다.",
            f"아직 채점한 퀴즈가 없으면 {_ui('이전 자료 가져오기')} 버튼이 보입니다. 예전 버전을"
            " 쓰던 분은 여기서 자료를 가져올 수 있습니다.",
        )
        + _tip(
            "처음이라면 홈에서 <b>＋ 새 퀴즈 채점</b>을 누르고,"
            " <a href='#new_quiz'>새 퀴즈 채점</a> 장을 순서대로 따라 하세요."
        )
    )


def _new_quiz() -> str:
    return (
        _anchor("new_quiz")
        + "<p>채점은 세 단계입니다. 화면 위에서 아래로 차례대로 진행합니다.</p>"
        + _flow(
            (
                ("① 학생 응답", "구글 폼 응답 파일 고르기"),
                ("② 문항표", "해설 자료 넣기<br>(없어도 됨)"),
                ("③ 채점하고<br>리포트 만들기", "버튼 한 번"),
            )
        )
        + f"<h3>① {escape('학생 응답')}</h3>"
        + _steps(
            "구글 폼의 응답 탭에서 <b>응답 다운로드(.csv)</b>로 파일을 받습니다.",
            f"{_btn('응답 파일 선택')}을 눌러 그 파일을 고릅니다.",
            f"{_name('퀴즈 이름')} 칸을 확인합니다. 파일 이름에서 자동으로 채워지며, 고칠 수 있습니다."
            " 이 이름이 퀴즈 목록과 리포트에 표시됩니다.",
            "고른 파일 아래에 채점할 학생 수와 제외되는 응답 수가 나오는지 확인합니다.",
        )
        + _grid(
            ("응답 파일", "설명"),
            (
                (
                    "구글 폼 CSV (권장)",
                    "문항마다 <b>[점수]</b> 열이 들어 있어, 문항표가 없어도 기본 리포트를 만들 수"
                    " 있습니다.",
                ),
                (
                    "연결된 스프레드시트 xlsx",
                    "문항별 정답 여부가 없습니다. 이 파일은 <b>문항표가 있어야</b> 채점됩니다.",
                ),
            ),
            "100%",
        )
        + "<h3>마감 시각과 제외되는 응답</h3>"
        + "<p>수업 시간에 푼 뒤, 학생들이 복습하려고 같은 폼을 다시 푸는 일이 있습니다."
        " 그런 응답이 점수에 섞이지 않게 마감 시각을 정합니다.</p>"
        + _bullets(
            f"응답이 {int(SITTING_GAP.total_seconds() // 60)}분 넘게 끊겨 여러 번에 나뉘어 있으면,"
            " 프로그램이 가장 응답이 많은 시간대의 마지막 응답 시각을 마감으로 제안하고"
            " 체크 상자를 켭니다.",
            f"체크 상자 {_name('이 시각 뒤 응답은 제외 (나중에 복습으로 다시 푼 것)')}를 켜면 그"
            " 시각 뒤에 낸 응답은 채점하지 않습니다. 시각은 직접 고칠 수 있습니다.",
            "같은 학번으로 여러 번 낸 응답은 <b>첫 응답만</b> 채점합니다.",
            "제외된 응답은 지워지지 않고, 결과 엑셀의 '제외된 응답' 시트에 이유와 함께 남습니다.",
        )
        + "<h3>학번 확인</h3>"
        + "<p>학번이 8자리 숫자가 아니면 오타일 수 있습니다. 그 학생은 채점에는 들어가지만"
        " 결과에서 노랗게 표시되고, 리포트에는 '학번 확인 필요'로 나옵니다. 개별 PDF의 파일"
        " 이름에는 <b>학번확인필요</b>가 들어갑니다. 구글 폼에서 학번을 고친 뒤 다시 채점하세요.</p>"
        + f"<h3>② {escape('정답·해설 (문항표)')}</h3>"
        + "<p>이미 본 구글 폼 퀴즈의 정답과 해설(틀린 이유)을 문항표로 만듭니다. 이 표가 있어야 학생마다"
        " '왜 틀렸는지'가 리포트에 들어갑니다. 없으면 점수와 정답만 담은 기본 리포트가 나갑니다."
        f" {_btn('폼 주소로 정답/해설 만들기')}부터 시작하세요. 자세한 방법은"
        " <a href='#question_bank'>문항표와 AI 프롬프트</a> 장을 보세요.</p>"
        + f"<h3>③ {escape('채점하고 리포트 만들기')}</h3>"
        + _steps(
            f"{_btn('채점하고 리포트 만들기')}를 누릅니다. 응답을 고르기 전에는 눌러지지 않습니다.",
            "프로그램이 퀴즈를 스스로 저장합니다. 저장할 폴더를 고를 필요가 없습니다.",
            f"끝나면 {_ui('리포트 열기')}와 {_ui('폴더 열기')} 중에서 고릅니다.",
            "새 퀴즈 카드가 홈의 맨 앞에 나타납니다.",
        )
        + _tip(
            "채점이 끝난 퀴즈는 언제든 <a href='#quiz_list'>퀴즈 목록</a>에서 다시 열 수 있습니다."
        )
    )


def _question_bank() -> str:
    headers = ", ".join(BANK_HEADERS)
    column_rows = (
        (_name("번호"), "문항 번호. 1번부터 차례대로."),
        (_name("단원"), "문항이 속한 단원(영역) 이름. 리포트의 단원별 정답률에 쓰입니다."),
        (_name("문제"), "문제 글. 구글 폼의 문제 글자와 같아야 합니다."),
        (_name("보기1 ~ 보기5"), "다섯 개의 보기. 구글 폼의 보기와 같아야 합니다."),
        (_name("정답"), "정답 번호(1~5)."),
        (_name("해설"), "정답을 설명하는 글."),
        (
            _name("오답이유1 ~ 오답이유5"),
            "각 보기를 골랐을 때 왜 틀렸는지. 정답 보기는 비워 둡니다.",
        ),
        (_name("함정유형1 ~ 함정유형5"), "각 보기가 어떤 함정인지. 아래 8가지 이름 중 하나입니다."),
        (_name("복습포인트"), "틀린 학생이 다시 볼 한 줄 요약."),
    )
    trap_rows = tuple((_name(name), escape(note, quote=False)) for name, note in TRAP_TYPES)
    return (
        _anchor("question_bank")
        + "<p>문항표는 문제, 보기, 정답, 해설, 보기별 오답 이유를 한 줄에 한 문항씩 적은 표입니다."
        " 직접 쓰는 것이 아니라 <b>AI에게 맡깁니다</b>. 프로그램이 AI에게 줄 프롬프트를 만들고,"
        " AI가 준 표를 다시 프로그램에 넣습니다.</p>"
        + "<h3>표의 열</h3>"
        + f"<p>엑셀 파일이면 시트 이름은 <b>{escape(BANK_SHEET)}</b>이고 첫 줄은 아래 열 이름입니다."
        " 열 이름은 글자 그대로여야 합니다.</p>"
        + _grid(("열", "내용"), column_rows, "100%")
        + f"<p class='muted'>첫 줄 전체: {escape(headers)}</p>"
        + "<h3>함정 유형</h3>"
        + "<p>함정유형 칸에는 다음 여덟 가지 이름만 씁니다. 같은 함정에 몇 명이 걸렸는지"
        " 채점결과 엑셀의 '학생별 함정'·'반 전체 함정' 시트에서 볼 수 있습니다.</p>"
        + _grid(("이름", "뜻"), trap_rows, "100%")
        + "<h3>쉬운 말, 짧은 글</h3>"
        + f"<p>학생이 한눈에 읽도록 <b>오답이유는 {READABLE_LIMIT}자 이내</b>, 해설은"
        f" {READABLE_LIMIT * 2}자 이내로 씁니다. 더 긴 글은 문항표를 넣을 때 '학생이 읽기에 긴"
        " 문장'으로 알려 줍니다. 그때 해설 만들기 프롬프트로 AI에게 쉽게 줄여 달라고 하면"
        " 됩니다.</p>"
        + "<h3>가. 폼 주소로 정답/해설 만들기</h3>"
        + _steps(
            "① 단계에서 응답 파일을 먼저 고릅니다. 구글 폼 CSV면 정답을 응답의 점수 열에서 가져옵니다.",
            "학생이 푼 구글 폼의 주소(https://docs.google.com/forms/…)를 붙여 넣고"
            f" {_btn('폼 주소로 정답/해설 만들기')}를 누릅니다. 폼이 공개되어 있어야 읽을 수 있습니다.",
            "문제, 보기(폼 순서 그대로), 정답이 채워진 문항표 틀이 생깁니다. 해설, 오답이유, 함정유형,"
            " 복습포인트는 아직 비어 있습니다.",
        )
        + _warn(
            "응답 파일이 스프레드시트(xlsx)면 정답 표시가 없어 <b>추가 작업이 필요합니다</b>. 틀의 정답 칸이"
            " 비어 있으니, '나'에서 AI에게 정답과 해설을 함께 받으세요. 구글 폼 응답 탭에서 CSV로 받으면"
            " 정답이 자동으로 들어갑니다."
        )
        + "<h3>나. AI에게 정답/해설 받기</h3>"
        + _steps(
            f"{_btn('해설 만들기 프롬프트 복사')}를 누릅니다. 지금 문항표와 채울 칸, 고칠 점이 담깁니다.",
            "AI 대화창(ChatGPT, Claude, Gemini 등)에 붙여 넣습니다. 학생 이름·학번은 들어가지 않습니다.",
            "AI가 준 표를 아래 'AI가 준 표 넣기' 방법으로 넣습니다. 빈 정답도 AI가 채웁니다.",
        )
        + "<h3>AI가 준 표 넣기</h3>"
        + _bullets(
            f"AI가 대화창에 표로 답했으면 그 표 전체를 복사(Ctrl+C)한 뒤"
            f" {_btn('문항표 클립보드에서 붙여넣기')}를 누릅니다.",
            f"AI가 엑셀 파일(.xlsx)로 주었으면 {_btn('문항표 파일 불러오기')}로 고릅니다.",
            "넣은 뒤 화면에 문항 수와 상태가 나옵니다. 빈 칸이나 고칠 문장이 있으면 목록으로"
            f" 알려 줍니다. 그때는 {_btn('해설 만들기 프롬프트 복사')}를 눌러 AI에게 고쳐 달라고"
            " 하고, 새 표를 다시 넣습니다. 고칠 점도 프롬프트에 함께 들어갑니다.",
            f"{_btn('문항표 내보내기')}는 지금 문항표를 엑셀로 저장합니다(보관하거나 직접 고칠 때).",
            f"{_btn('문항표 지우기')}는 화면에서만 뺍니다. 파일은 지워지지 않습니다.",
        )
        + _grid(
            ("문항표 상태", "리포트"),
            (
                ("완성", "문항마다 해설, 틀린 이유, 함정 유형, 복습 포인트가 들어갑니다."),
                ("빈 칸이 있는 문항", "그 문항만 기본 리포트(정답만, 해설 없음)로 나갑니다."),
                (
                    "문항표 없음",
                    "구글 폼 CSV의 문항별 점수로 기본 리포트를 만듭니다. 정답만 알려 주고 해설은"
                    " 없습니다. 연결된 스프레드시트 xlsx 응답은 문항표가 없으면 채점되지 않습니다.",
                ),
            ),
            "100%",
        )
        + _warn(
            "문항표의 문제 글자와 보기, 문항 수와 순서는 구글 폼과 같아야 합니다. 다르면 채점할 때"
            " 어느 문항이 다른지 알려 주고 멈춥니다."
        )
        + _privacy(
            "프롬프트에는 문제, 보기, 정답만 들어갑니다. 학생 이름이나 학번을 AI 대화창에 붙여"
            " 넣지 마세요. 응답 파일을 AI에게 보내지 마세요."
        )
    )


def _reports() -> str:
    return (
        _anchor("reports")
        + "<p>채점이 끝나면 퀴즈 폴더의 <b>리포트</b> 폴더에 다음 파일이 만들어집니다.</p>"
        + _grid(
            ("파일", "내용"),
            (
                (
                    _name("전체(인쇄용).pdf"),
                    "모든 학생을 한 파일에 담았습니다. 학생당 1쪽이고, 이름 가나다순입니다."
                    " 한 번에 인쇄할 때 씁니다.",
                ),
                (
                    "<span class='ui'>개별\\&lt;순번&gt;_&lt;학번&gt;_&lt;이름&gt;.pdf</span>",
                    f"학생마다 한 파일입니다. 예: {_EXAMPLE_FILE}. 학생에게 따로 보낼 때 씁니다.",
                ),
                (
                    _name("채점결과.xlsx"),
                    "선생님용 엑셀로, 리포트 폴더가 아니라 퀴즈 폴더에 있습니다. 첫 시트 '채점결과'에"
                    " 학생마다 고른 답이 나오고(틀린 답 분홍, 답 없음 회색, 학번 확인 필요 노랑),"
                    " 이어서 문항 분석, 학생별 함정, 반 전체 함정, 제외된 응답, 문항표, 색 설명"
                    " 시트가 있습니다.",
                ),
            ),
            "100%",
        )
        + "<h3>학생 한 쪽에 들어 있는 것</h3>"
        + _bullets(
            "<b>점수</b>: 학생 점수와 반 평균을 나란히 보여 줍니다.",
            "<b>단원별 정답률</b>: 단원마다 맞힌 정도.",
            "<b>틀린 문항</b>: 문항마다 학생이 고른 보기, 정답, 연한 분홍색 <b>틀린 이유</b> 상자,"
            " 함정 유형이 나옵니다.",
            "<b>복습 포인트</b>: 가장 먼저 다시 볼 내용을 최대 세 개까지 모아 보여 줍니다.",
        )
        + "<p>문항표가 없거나 문항에 빈 칸이 있으면 그 부분은 정답만 나오고 해설과 틀린 이유는"
        " 없습니다.</p>"
        + "<p>문항표 없이 응답 CSV의 점수만으로 채점하면 프로그램이 폼의 보기 순서를 알 수 없습니다."
        " 그래서 리포트에는 보기 번호(①~⑤) 없이 보기 글자만 나오고, 채점결과 엑셀의 번호는 응답에"
        " 처음 나온 순서를 따릅니다. 폼 순서대로 번호를 쓰려면 공개 폼 주소로 문항표 틀을 만드세요.</p>"
        + "<h3>채점결과.xlsx</h3>"
        + "<p>퀴즈 폴더에는 <b>채점결과.xlsx</b>도 함께 저장됩니다. 시트는 <b>채점결과</b>,"
        " <b>문항 분석</b>, <b>학생별 함정</b>, <b>반 전체 함정</b>, <b>문항표</b>, <b>색 설명</b>"
        "입니다. 마감 뒤 응답이나 같은 학번의 두 번째 응답이 있으면 <b>제외된 응답</b> 시트가"
        " 더해져 어느 응답이 왜 빠졌는지 보여 줍니다.</p>"
        + _tip(
            "리포트를 다시 열려면 홈 카드의 "
            f"{_ui('리포트')} 버튼이나 <a href='#quiz_list'>퀴즈 목록</a>을 쓰세요."
        )
    )


def _quiz_list() -> str:
    return (
        _anchor("quiz_list")
        + "<p>지금까지 채점한 퀴즈가 최신 순으로 표에 나옵니다.</p>"
        + _grid(
            ("열", "내용"),
            (
                (_name("날짜"), "채점한 날짜."),
                (_name("퀴즈명"), "채점할 때 정한 이름."),
                (_name("인원"), "채점한 학생 수."),
                (_name("평균"), "반 평균 점수."),
                (
                    _name("리포트"),
                    "<b>상세</b>(문항표로 만든 리포트) 또는 <b>기본</b>(정답만 있는 리포트).",
                ),
            ),
            "100%",
        )
        + "<p>퀴즈를 고른 뒤 아래 버튼을 씁니다.</p>"
        + _grid(
            ("버튼", "하는 일"),
            (
                (_ui("리포트 열기"), "인쇄용 묶음 PDF를 엽니다."),
                (_ui("폴더 열기"), "그 퀴즈의 폴더를 탐색기로 엽니다."),
                (
                    _ui("문항표 바꿔 다시 만들기"),
                    "다른 문항표를 넣어 저장해 둔 원본 응답으로 다시 채점하고, 리포트를 새로"
                    " 만듭니다. <b>이전 리포트는 새 리포트로 바뀝니다.</b>",
                ),
                (_ui("삭제"), "퀴즈를 휴지통으로 옮깁니다. 바로 지워지지는 않습니다."),
                (_ui("휴지통 보기"), "휴지통 창을 엽니다."),
            ),
            "100%",
        )
        + "<h3>휴지통</h3>"
        + _bullets(
            f"{_ui('복원')}: 선택한 퀴즈를 퀴즈 목록으로 되돌립니다.",
            f"{_ui('영구 삭제')}: 휴지통에서도 지웁니다. 되돌릴 수 없습니다.",
        )
        + "<h3>읽을 수 없는 퀴즈</h3>"
        + "<p>목록에서 읽을 수 없는 퀴즈는 회색으로 나오고, 읽을 수 없는 이유가 함께 표시됩니다."
        " 그 퀴즈의 리포트 열기와 다시 만들기는 쓸 수 없습니다.</p>"
        + _warn(
            "그 퀴즈의 PDF나 엑셀이 열려 있으면 삭제와 다시 만들기는 멈추고, 파일을 닫으라고"
            " 알려 줍니다. 파일을 닫은 뒤 다시 누르세요."
        )
    )


def _settings() -> str:
    return (
        _anchor("settings")
        + _grid(
            ("항목", "설명"),
            (
                (
                    _name("1. 저장 위치"),
                    "자료가 저장되는 Data 폴더가 표시됩니다. "
                    f"{_ui('폴더 열기')}로 탐색기에서 엽니다. 저장 위치는 바꿀 수 없습니다."
                    " 옮기고 싶으면 프로그램 폴더 전체를 옮기세요.",
                ),
                (
                    _name("2. 새 버전 안내"),
                    "체크 상자 <b>하루 한 번 새 버전 확인</b>을 켜면 하루에 한 번 최신 버전 번호를"
                    f" 묻습니다. {_ui('지금 확인')}으로 바로 확인할 수도 있습니다. 보내는 것은"
                    " 프로그램 버전 번호뿐이고, 새 버전을 자동으로 설치하지 않습니다.",
                ),
                (
                    _name("3. 이전 자료 가져오기"),
                    f"{_ui('이전 자료 가져오기')}를 누르고 예전 프로그램 폴더를 고릅니다. 퀴즈와"
                    " 휴지통을 확인한 뒤 복사해 옵니다. 예전 폴더는 바뀌지 않습니다. 이미 있는"
                    " 퀴즈는 건너뛰므로 다시 실행해도 안전합니다.",
                ),
            ),
            "100%",
        )
        + _tip("새 버전으로 옮기는 순서는 <a href='#files'>폴더와 업데이트</a> 장에 있습니다.")
    )


def _files() -> str:
    tree = (
        "D:\\Quiz-Reporter\\\n"
        "├─ Quiz Reporter.exe\n"
        "├─ _internal\\\n"
        "└─ Data\\\n"
        "   ├─ FORMAT.json\n"
        "   ├─ &lt;yymmdd&gt;_&lt;HHMMSS&gt;_&lt;퀴즈명&gt;\\\n"
        "   │  ├─ 퀴즈정보.json\n"
        "   │  ├─ 문항표.xlsx\n"
        "   │  ├─ 응답원본.csv\n"
        "   │  ├─ 채점결과.xlsx\n"
        "   │  └─ 리포트\\\n"
        "   │     ├─ 전체(인쇄용).pdf\n"
        "   │     └─ 개별\\&lt;순번&gt;_&lt;학번&gt;_&lt;이름&gt;.pdf\n"
        "   └─ _휴지통\\"
    )
    return (
        _anchor("files")
        + "<p>퀴즈 리포터는 설치하지 않는 포터블 프로그램입니다. 폴더 하나가 프로그램이면서"
        " 자료 보관함입니다.</p>"
        + f"<pre>{tree}</pre>"
        + _grid(
            ("이름", "무엇인가"),
            (
                (_name("Quiz Reporter.exe"), "프로그램. 더블클릭해서 실행합니다."),
                (_name("_internal"), "프로그램이 쓰는 부품. EXE와 같은 폴더에 있어야 합니다."),
                (_name("Data"), "모든 퀴즈 자료. 퀴즈마다 폴더가 하나씩 있습니다."),
                (_name("FORMAT.json"), "자료 형식 표시. 프로그램이 관리합니다."),
                (_name("퀴즈정보.json"), "퀴즈 이름, 날짜, 인원 같은 정보. 프로그램이 관리합니다."),
                (_name("문항표.xlsx"), "그 퀴즈에 쓴 문항표."),
                (_name("응답원본.csv"), "채점한 응답 파일의 사본. 다시 만들기에 씁니다."),
                (
                    _name("채점결과.xlsx"),
                    "학생별 고른 답과 점수, 문항 분석, 함정 통계를 담은 엑셀.",
                ),
                (_name("리포트"), "인쇄용 묶음 PDF와 학생별 PDF."),
                (_name("_휴지통"), "삭제한 퀴즈가 머무는 곳."),
            ),
            "100%",
        )
        + _warn(
            "<b>퀴즈정보.json</b>과 <b>FORMAT.json</b>은 직접 고치거나 지우지 마세요. 퀴즈를"
            " 못 읽게 될 수 있습니다."
        )
        + "<h3>새 버전으로 옮기기</h3>"
        + _steps(
            "새 버전 ZIP을 <b>새 폴더</b>에 풉니다. 예전 폴더 위에 덮어쓰지 않습니다.",
            "새 프로그램을 실행하고 "
            f"{_ui('설정')} → {_ui('이전 자료 가져오기')}에서 예전 프로그램 폴더를 고릅니다.",
            "퀴즈가 모두 옮겨졌는지 확인합니다. 예전 폴더는 그대로 남아 있습니다.",
        )
        + "<h3>둘 곳</h3>"
        + _bullets(
            "쓰기가 되는 전용 폴더(예: D:\\Quiz-Reporter)에 두세요.",
            "<b>C:\\Program Files</b>나 읽기 전용 USB·디스크, 동기화 프로그램이 계속 잠그는"
            " 폴더는 피하세요.",
            "EXE만 따로 옮기지 말고 폴더 전체를 옮기세요.",
        )
        + "<h3>'읽기 전용으로 열었습니다'라고 나올 때</h3>"
        + "<p>이 경우 퀴즈를 볼 수는 있지만 새로 채점하거나 바꿀 수 없습니다. 이유는 둘 중 하나입니다.</p>"
        + _bullets(
            "<b>더 새 버전의 자료입니다.</b> 이 폴더의 자료를 더 새 퀴즈 리포터가 만들었습니다."
            " 자료를 보호하려고 읽기 전용으로 엽니다. 새 버전으로 여세요.",
            "<b>쓰기 권한이 없습니다.</b> 프로그램을 끄고 폴더 전체를 쓰기가 되는 곳으로 옮긴 뒤"
            " 다시 실행하세요.",
        )
    )


def _trouble() -> str:
    items = (
        (
            "xlsx 응답이라 채점이 안 돼요.",
            "연결된 스프레드시트 xlsx에는 문항별 정답 여부가 없습니다. 구글 폼 응답 탭의"
            " <b>응답 다운로드(.csv)</b>로 받은 CSV를 쓰거나, xlsx로 채점하려면 문항표를 먼저"
            " 넣으세요. <a href='#question_bank'>문항표와 AI 프롬프트</a>를 보세요.",
        ),
        (
            "문항표가 폼과 다르다고 나와요.",
            "문항표의 문제 글자와 보기, 문항 수와 순서가 구글 폼과 같아야 합니다. 안내에 나온 문항을 폼과"
            " 맞춰 고치세요. 폼에서 직접 틀을 만들면 글자가 같게 만들어집니다.",
        ),
        (
            "학생 학번이 '학번확인필요'로 나와요.",
            "응답의 학번이 8자리 숫자가 아닙니다(글자가 섞였거나 자릿수가 다름). 그 학생은 채점은"
            " 되지만 결과에서 노랗게 표시됩니다. 구글 폼의 응답을 고치고 다시 채점하세요.",
        ),
        (
            "파일이 열려 있다고 나와요.",
            "그 퀴즈의 PDF나 엑셀, 또는 퀴즈 폴더를 연 탐색기 창이 열려 있습니다. 모두 닫고 다시"
            " 시도하세요.",
        ),
        (
            "프로그램을 두 번 실행했더니 안내 후 꺼졌어요.",
            "같은 폴더의 프로그램은 한 번에 하나만 실행할 수 있습니다. 먼저 실행한 창을"
            " 사용하세요. 보이지 않으면 작업 표시줄을 확인하세요.",
        ),
        (
            "예전 퀴즈가 보이지 않아요.",
            f"새 폴더에서 처음 실행했다면 {_ui('설정')}의 {_ui('이전 자료 가져오기')}로 예전 폴더를"
            " 고르세요.",
        ),
    )
    body = "".join(f"<h3>Q. {question}</h3><p>{answer}</p>" for question, answer in items)
    return _anchor("trouble") + body


def _about() -> str:
    rows = (
        ("프로그램", f"퀴즈 리포터 (Quiz Reporter) v{escape(quiz_reporter.__version__)}"),
        ("만든 사람", "조승현 (Cho, Seung-Hyun)"),
        ("연락처", "kaic21@gmail.com"),
        ("홈페이지·새 버전", escape(HOMEPAGE)),
        ("저작권", "Copyright (c) 2026 조승현 (Cho, Seung-Hyun)"),
    )
    return (
        _anchor("about")
        + _grid(("항목", "내용"), rows, "100%")
        + "<h3>라이선스</h3>"
        + "<p>퀴즈 리포터는 <b>PolyForm Noncommercial License 1.0.0</b>으로 배포합니다(프로그램 폴더의"
        " LICENSE.md). 개인의 공부·연구와 학교·공공기관·비영리단체에서는 무료로 쓰고, 고치고, 나눠 줄 수"
        " 있습니다. 판매 등 <b>상업적 이용은 허락되지 않습니다</b>. 상업적 이용 문의: kaic21@gmail.com."
        " 프로그램은 있는 그대로 제공되며, 사용으로 생긴 손해에 만든 사람은 책임지지 않습니다.</p>"
        + "<h3>함께 쓰는 부품</h3>"
        + _bullets(
            "<b>Qt for Python(PySide6)과 Qt</b> — GNU LGPL 3.0. 프로그램 폴더 _internal 안의 Qt 파일은"
            " 고치지 않은 그대로이며, 직접 고치거나 바꿔 끼울 수 있습니다.",
            "<b>openpyxl, et-xmlfile</b> — MIT 라이선스 (엑셀 파일)",
            "<b>Python</b> — PSF 라이선스, 함께 들어 있는 OpenSSL(Apache 2.0)·libffi·expat(MIT)·"
            "mpdecimal(BSD)·xz·zlib·bzip2",
            "<b>PyInstaller 실행기</b> — GPL 2.0 이상(실행 파일 예외 조항 포함)",
        )
        + "<p>각 부품의 저작권과 라이선스 전문은 프로그램 폴더의 <b>THIRD_PARTY_NOTICES.txt</b>에"
        " 있습니다.</p>"
        + _tip(
            "학생 자료는 이 PC의 프로그램 폴더에만 저장되고, 새 버전 확인 때는 버전 번호만 보냅니다."
        )
    )


def help_html() -> str:
    """The whole manual as one document; each section starts at an anchor named by its key."""
    return (
        "<html><body>"
        "<h1>퀴즈 리포터 도움말</h1>"
        "<p class='lead'>왼쪽 목차를 누르거나 위 검색 칸에 찾는 말을 적으세요.</p>"
        + _home()
        + _new_quiz()
        + _question_bank()
        + _reports()
        + _quiz_list()
        + _settings()
        + _files()
        + _trouble()
        + _about()
        + "</body></html>"
    )


__all__ = [
    "HELP_STYLESHEET",
    "PAGE_SECTIONS",
    "SECTIONS",
    "HelpSection",
    "help_html",
]
