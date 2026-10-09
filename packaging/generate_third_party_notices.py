"""Write THIRD_PARTY_NOTICES.txt for a Quiz Reporter release folder.

The text is generated from the distributions installed in the build environment, so it always
names the versions that were really bundled. Usage:

    python packaging/generate_third_party_notices.py <output file>

It is a notice file, not a legal opinion. Qt is used under the LGPL; the other licenses are the
ones the packages themselves ship.
"""

from __future__ import annotations

import sys
from argparse import ArgumentParser
from importlib.metadata import Distribution, PackageNotFoundError, distribution
from pathlib import Path

HERE = Path(__file__).resolve().parent
LGPL_TEXT = HERE / "licenses" / "LGPL-3.0.txt"
GPL_TEXT = HERE / "licenses" / "GPL-3.0.txt"
RULE = "=" * 72
QT_SOURCE_URL = "https://download.qt.io"
PYSIDE_SOURCE_URL = "https://code.qt.io/cgit/pyside/pyside-setup.git"
LGPL_URL = "https://www.gnu.org/licenses/lgpl-3.0.html"
GPL_URL = "https://www.gnu.org/licenses/gpl-3.0.html"
PYTHON_LICENSE_URL = "https://docs.python.org/3/license.html"


def _dist(name: str) -> Distribution:
    try:
        return distribution(name)
    except PackageNotFoundError as error:
        raise RuntimeError(f"A bundled distribution is not installed: {name}") from error


def _license_files(dist: Distribution) -> list[tuple[str, str]]:
    """(file name, text) of the license files a distribution declares in its metadata."""
    names = dist.metadata.get_all("License-File") or []
    found: list[tuple[str, str]] = []
    for name in names:
        text = dist.read_text(f"licenses/{name}") or dist.read_text(name)
        if text:
            found.append((Path(name).name, text.strip()))
    return found


def _section(title: str, body: str) -> str:
    return f"{RULE}\n{title}\n{RULE}\n\n{body.strip()}\n"


def _qt_section() -> str:
    pyside = _dist("PySide6_Essentials")
    shiboken = _dist("shiboken6")
    version = pyside.version
    declared = pyside.metadata.get("License-Expression") or pyside.metadata.get("License") or ""
    body = f"""\
Qt for Python (PySide6 {version}, shiboken6 {shiboken.version}) and the Qt {version} libraries
  Declared in the package metadata: {declared}
  Used here under: GNU Lesser General Public License, version 3 (LGPL-3.0)

이 프로그램은 Qt를 GNU LGPL 3.0 조건으로 사용합니다. Qt 파일은 고치지 않고 그대로 넣었고, 쓰지
않는 Qt 모듈은 뺐습니다. Qt가 들어 있는 곳은 이 폴더의 _internal 폴더(특히 _internal\\PySide6)입니다.

Qt is used under the terms of the GNU Lesser General Public License version 3. The Qt
libraries are included unmodified as separate DLL and extension files in the "_internal"
folder (mainly "_internal\\PySide6"); modules this program does not use are left out. Quiz
Reporter's own source code is under its own license (see LICENSE.md); the LGPL covers Qt only.
Nothing in Quiz Reporter's license restricts you from modifying the Qt libraries in
"_internal" for your own use, or from reverse engineering to debug such modifications
(GNU LGPL-3.0, section 4).

Source code of Qt {version} and Qt for Python {version} (the exact version bundled here):
  Qt:           {QT_SOURCE_URL}
  Qt for Python: {PYSIDE_SOURCE_URL}  (tag v{version})

You may replace the Qt libraries with your own build of the same Qt version: put your
Qt DLLs (and the PySide6 / shiboken6 files) over the ones in "_internal" and the program will
use them. The full license texts follow: the LGPL-3.0, then the GNU GPL-3.0 it builds on
({GPL_URL}).

Qt also contains third-party components under their own licenses; see
https://doc.qt.io/qt-6/licenses-used-in-qt.html.

The Microsoft Visual C++ runtime DLLs (msvcp140*.dll, vcruntime140*.dll) shipped with Python
and Qt are redistributed under Microsoft's redistribution terms.

--- GNU LESSER GENERAL PUBLIC LICENSE, Version 3 ({LGPL_URL}) ---

{_read_lgpl()}

--- GNU GENERAL PUBLIC LICENSE, Version 3 ({GPL_URL}) ---

{_read_gpl()}
"""
    return _section("Qt for Python (PySide6) and Qt - LGPL-3.0", body)


def _read_gpl() -> str:
    if not GPL_TEXT.is_file():
        raise RuntimeError(f"The GPL-3.0 text is missing: {GPL_TEXT}")
    return GPL_TEXT.read_text(encoding="utf-8").strip()


def _read_lgpl() -> str:
    if not LGPL_TEXT.is_file():
        raise RuntimeError(f"The LGPL-3.0 text is missing: {LGPL_TEXT}")
    return LGPL_TEXT.read_text(encoding="utf-8").strip()


def _package_section(name: str, title: str) -> str:
    dist = _dist(name)
    files = _license_files(dist)
    if not files:
        raise RuntimeError(f"No license file in the metadata of {name}")
    declared = dist.metadata.get("License-Expression") or dist.metadata.get("License") or ""
    parts = [f"{name} {dist.version}", f"  Declared in the package metadata: {declared}", ""]
    for file_name, text in files:
        parts.extend((f"--- {file_name} ---", "", text, ""))
    return _section(title, "\n".join(parts))


def _pyinstaller_section() -> str:
    dist = _dist("PyInstaller")
    text = dist.read_text("COPYING.txt")
    if not text:
        raise RuntimeError("PyInstaller's COPYING.txt is missing from its metadata")
    body = f"""\
PyInstaller {dist.version}
  The program's launcher (the bootloader inside Quiz Reporter.exe) and its runtime hooks come
  from PyInstaller, which is under the GNU General Public License v2 or later WITH a special
  exception that allows distributing programs built with it under any license. The exception
  is quoted below.

--- COPYING.txt ---

{text.strip()}
"""
    return _section("PyInstaller (launcher) - GPL-2.0-or-later with bootloader exception", body)


def _python_section() -> str:
    license_file = Path(sys.base_prefix) / "LICENSE.txt"
    version = sys.version.split()[0]
    if license_file.is_file():
        text = license_file.read_text(encoding="utf-8", errors="replace").strip()
    else:
        text = f"The license file was not found next to this Python. See {PYTHON_LICENSE_URL}"
    body = f"""\
Python {version}
  The Python interpreter and standard library are bundled in "_internal".
  License: Python Software Foundation License (PSF)

{text}
"""
    return _section("Python - PSF License", body)


def render() -> str:
    """The full text of THIRD_PARTY_NOTICES.txt."""
    intro = """\
퀴즈 리포터(Quiz Reporter)에 함께 들어 있는 제3자 소프트웨어의 고지입니다.
Notices for the third-party software bundled with Quiz Reporter.

Quiz Reporter 자체의 사용 조건은 LICENSE.md를 보세요. / See LICENSE.md for Quiz Reporter itself.
"""
    sections = [
        intro,
        _qt_section(),
        _package_section("openpyxl", "openpyxl - MIT"),
        _package_section("et-xmlfile", "et-xmlfile - MIT"),
        _pyinstaller_section(),
        _python_section(),
    ]
    return "\n".join(sections)


def write_notices(output: Path) -> Path:
    """Write the notices to ``output`` (UTF-8, Windows line ends) and return it."""
    text = render().replace("\r\n", "\n")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8", newline="\r\n")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Write THIRD_PARTY_NOTICES.txt")
    parser.add_argument("output", type=Path, help="file to write; it must not exist yet")
    args = parser.parse_args(argv)
    if args.output.exists():
        print(f"Refusing to overwrite {args.output}", file=sys.stderr)
        return 1
    write_notices(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
