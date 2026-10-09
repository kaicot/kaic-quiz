# 퀴즈 리포터

구글 폼 퀴즈 채점 · 학생별 피드백

> **개발 중입니다.** 첫 배포 버전은 1.0.0입니다. 아직 배포 파일이 없으며, 아래 내용은 1.0.0에 들어갈
> 기능을 기준으로 씁니다. 바뀐 점은 [CHANGELOG.md](CHANGELOG.md)에 남깁니다.

구글 폼으로 본 5지선다 퀴즈의 응답 파일을 채점하고, 학생마다 "왜 틀렸는지"를 알려 주는 피드백 리포트를
PDF로 만드는 Windows용 포터블 프로그램입니다.

## 주요 기능

- 구글 폼 응답 CSV(권장) 또는 연결된 스프레드시트 xlsx로 채점
- 수업 시간대 뒤에 다시 푼 응답(복습)은 마감 시각으로 자동 제외, 같은 학번은 첫 응답만 사용
- 문항표(문제·보기·정답·해설·오답 이유·함정 유형·복습 포인트)로 학생별 피드백
  - 문항표는 AI에게 맡깁니다. 화면의 **출제 프롬프트 복사**, **해설 만들기 프롬프트 복사**로 프롬프트를
    만들고, AI가 준 표를 붙여넣거나 xlsx로 불러옵니다.
  - 문항표가 없어도 구글 폼 CSV의 문항별 점수로 기본 리포트를 만듭니다.
- 리포트: 인쇄용 묶음 PDF(학생당 1쪽), 학생별 개별 PDF, 퀴즈 분석 엑셀
- 채점결과 엑셀: 채점결과, 문항 분석, 학생별 함정, 제외된 응답, 문항표
- 퀴즈 목록에서 리포트 다시 열기, 문항표를 바꿔 리포트 다시 만들기, 휴지통
- 새 버전 안내(하루 한 번 버전 번호만 확인, 자동 설치 없음)와 이전 버전 자료 가져오기

## 개인정보

- 학생 이름·학번·응답은 이 PC의 프로그램 폴더에만 저장합니다.
- AI에 보내는 프롬프트에는 문제·보기·정답만 들어갑니다. 학생 정보는 들어가지 않습니다.
- 새 버전 확인 때 보내는 정보는 프로그램 버전 번호뿐입니다.

## 포터블 사용 (1.0.0부터)

Python 설치는 필요 없습니다. 배포 ZIP을 쓰기 가능한 전용 폴더에 풀고 `Quiz Reporter.exe`를 실행합니다.
EXE와 `_internal\` 폴더를 함께 두어야 합니다. `C:\Program Files`처럼 쓰기가 제한된 곳은 피하세요.

```text
D:\Quiz-Reporter\
├─ Quiz Reporter.exe
├─ _internal\
└─ Data\
   ├─ FORMAT.json
   ├─ <yymmdd>_<HHMMSS>_<퀴즈명>\
   │  ├─ 퀴즈정보.json
   │  ├─ 문항표.xlsx
   │  ├─ 응답원본.csv
   │  ├─ 채점결과.xlsx
   │  └─ 리포트\
   │     ├─ 전체(인쇄용).pdf
   │     ├─ 퀴즈분석.xlsx
   │     └─ 개별\<순번>_<학번>_<이름>.pdf
   └─ _휴지통\
```

새 버전은 새 폴더에 풀고, 처음 실행할 때 **이전 버전 자료 가져오기**로 예전 폴더를 고릅니다. 예전 폴더는
바뀌지 않습니다.

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

개발 규칙은 [AGENTS.md](AGENTS.md)에 있습니다.
