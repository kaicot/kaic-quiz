# 퀴즈 리포터

구글 폼 퀴즈 채점 · 학생별 피드백

> **1.0.0 배포 준비 중입니다.** 배포 파일은 GitHub 릴리즈 페이지에 올라갑니다. 바뀐 점은
> [CHANGELOG.md](CHANGELOG.md)에 남깁니다.

구글 폼으로 본 5지선다 퀴즈의 응답 파일을 채점하고, 학생마다 "왜 틀렸는지"를 알려 주는 피드백 리포트를
PDF로 만드는 Windows용 포터블 프로그램입니다.

## 주요 기능

- 구글 폼 응답 CSV(권장) 또는 연결된 스프레드시트 xlsx로 채점
- 수업 시간대 뒤에 다시 푼 응답(복습)은 마감 시각으로 자동 제외, 같은 학번은 첫 응답만 사용
- 문항표(문제·보기·정답·해설·오답 이유·함정 유형·복습 포인트)로 학생별 피드백
  - 문항표는 AI에게 맡깁니다. 화면의 **출제 프롬프트 복사**, **해설 만들기 프롬프트 복사**로 프롬프트를
    만들고, AI가 준 표를 붙여넣거나 xlsx로 불러옵니다.
  - 문항표가 없어도 구글 폼 CSV의 문항별 점수로 기본 리포트를 만듭니다. 이때는 폼의 보기 순서를 알 수
    없어 리포트에 보기 번호 없이 보기 글자만 씁니다(공개 폼 주소로 문항표 틀을 만들면 번호도 나옵니다).
- 리포트: 인쇄용 묶음 PDF(학생당 1쪽), 학생별 개별 PDF. 흑백 인쇄에도 읽기 좋게 만들었습니다.
- 채점결과 엑셀 하나에 채점결과(고른 보기 번호를 숫자로, 틀린 답 분홍), 문항 분석, 학생별 함정,
  반 전체 함정, 제외된 응답, 문항표, 색 설명
- 퀴즈 목록에서 리포트 다시 열기, 문항표를 바꿔 리포트 다시 만들기, 휴지통
- 새 버전 안내(하루 한 번 버전 번호만 확인, 자동 설치 없음)와 이전 버전 자료 가져오기

## 개인정보

- 학생 이름·학번·응답은 이 PC의 프로그램 폴더에만 저장합니다. 다른 곳으로 보내지 않습니다.
- AI에 보내는 프롬프트에는 문제·보기·정답만 들어갑니다. 학생 정보는 들어가지 않습니다.
- 새 버전 확인 때 GitHub에 보내는 정보는 프로그램 버전 번호뿐입니다. 설정에서 끌 수 있습니다.

## 설치와 실행

Windows 10/11(64비트)에서 씁니다. Python은 필요 없습니다.

1. 릴리즈 페이지에서 `Quiz-Reporter-vX.Y.Z-windows.zip`을 받습니다.
2. 쓰기 가능한 전용 폴더(예: `D:\퀴즈리포터\`)에 풉니다. `C:\Program Files`나 바탕 화면 바로 아래,
   동기화 폴더는 피하세요.
3. 폴더 안의 `Quiz Reporter.exe`를 실행합니다. EXE만 따로 옮기지 말고 폴더째 둡니다.

```text
D:\퀴즈리포터\Quiz-Reporter-v1.0.0\
├─ Quiz Reporter.exe
├─ _internal\                 프로그램 부품(지우지 마세요)
├─ LICENSE.md                 이 프로그램의 라이선스
├─ THIRD_PARTY_NOTICES.txt    함께 쓰는 부품(Qt 등)의 라이선스
├─ update.json                새 버전 확인 설정(처음 실행 후)
├─ logs\                      실행 기록
└─ Data\                      모든 퀴즈 자료
   ├─ FORMAT.json
   ├─ <yymmdd>_<HHMMSS>_<퀴즈명>\
   │  ├─ 퀴즈정보.json
   │  ├─ 문항표.xlsx
   │  ├─ 응답원본.csv
   │  ├─ 채점결과.xlsx
   │  └─ 리포트\
   │     ├─ 전체(인쇄용).pdf
   │     └─ 개별\<순번>_<학번>_<이름>.pdf
   └─ _휴지통\
```

**새 버전으로 바꿀 때**: 새 ZIP을 새 폴더에 풀고, 새 프로그램의 **설정 → 이전 자료 가져오기**에서 예전
프로그램 폴더를 고릅니다. 예전 폴더는 바뀌지 않으니 새 버전을 확인한 뒤 직접 정리하세요.

## 라이선스

[PolyForm Noncommercial License 1.0.0](LICENSE.md)으로 배포합니다.

- 개인의 공부·연구, 학교·공공기관·비영리단체에서는 무료로 쓰고, 고치고, 나눠 줄 수 있습니다.
- 판매 등 **상업적 이용은 허락되지 않습니다.** 상업적 이용 문의: kaic21@gmail.com
- 다시 나눠 줄 때는 `LICENSE.md`의 `Required Notice` 줄을 그대로 함께 넣어야 합니다.
- 함께 쓰는 부품(Qt for Python 등)은 각자의 라이선스를 따릅니다(`THIRD_PARTY_NOTICES.txt`).
  PolyForm 라이선스는 퀴즈 리포터 자체 코드에만 적용되며, 프로그램 폴더 `_internal`의 Qt
  라이브러리(GNU LGPL-3.0)를 고치거나 그 수정을 디버깅하려고 역분석하는 것을 막지 않습니다.

Copyright (c) 2026 조승현 (Cho, Seung-Hyun) <kaic21@gmail.com>

## 소스에서 실행하기 (개발자용)

Windows, Python 3.12, [uv](https://docs.astral.sh/uv/)를 씁니다.

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv -c constraints/windows-py312.txt -e ".[dev]"
```

실행: `.venv\Scripts\python main.py` (저장소 폴더가 포터블 루트가 되어 `Data\`가 그 안에 생깁니다)

확인 절차(모두 통과해야 커밋합니다):

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.venv\Scripts\python -m pytest -q
.venv\Scripts\ruff check src tests
.venv\Scripts\ruff format --check src tests
.venv\Scripts\mypy
```

배포 폴더 만들기와 검증은 `tools\build-portable-folder.ps1`, `tools\verify-portable-folder.ps1`,
`tools\smoke-portable.py`를 씁니다(`uv pip install ... -e ".[dev,build]"` 필요).

개발 규칙은 [AGENTS.md](AGENTS.md)에 있습니다.
