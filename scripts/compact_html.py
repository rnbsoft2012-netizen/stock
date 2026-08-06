#!/usr/bin/env python3
"""
report.py가 만든 메일 HTML을 같은 모양 그대로 작게 줄인다.

카드가 23개라 인라인 style 속성이 910번 반복되고, 그게 본문의 59%를 차지한다
(69.5KB 중 40.8KB). 서로 다른 style 값은 44개뿐이므로 이를 `<style>` 블록의
클래스로 접으면 절반 이하로 줄어든다.

**왜 줄여야 하나**: 발송은 Zapier MCP 도구(`gmail_send_email`)의 `body`
파라미터로 이뤄지는데, 본문 전체가 도구 호출 인자로 들어가야 한다. 70KB짜리
HTML은 한 번에 다루기 버겁고, 그대로 옮겨 적는 과정에서 깨질 위험도 있다.

**Gmail에서 안전한가**: 받는 쪽이 Gmail 한 곳이고, Gmail 웹메일은 2016년부터
본문 내 `<style>` 블록을 지원한다. 만약 어떤 클라이언트가 `<style>`을 버리더라도
글자는 그대로 남고 색·여백만 빠진다 — 내용이 사라지지는 않는다.

사용법:
    python scripts/report.py NOTES BRIEF [TECH] > report.json
    python scripts/compact_html.py report.json > report_compact.json

출력은 입력과 같은 {"subject", "html"} JSON이다.
"""
import json
import re
import sys
from collections import Counter

STYLE_ATTR = re.compile(r"""\sstyle=(['"])(.*?)\1""", re.S)


def compact(html: str) -> str:
    styles = [m.group(2) for m in STYLE_ATTR.finditer(html)]
    if not styles:
        return html

    # 자주 쓰이는 순서대로 짧은 이름을 준다. 한 번만 쓰이고 짧은 style은
    # 클래스로 바꿔봐야 손해라서 인라인으로 남긴다.
    counts = Counter(styles)
    names: dict[str, str] = {}
    for i, (style, n) in enumerate(counts.most_common()):
        cls = _name(i)
        # 인라인 유지 비용: n * (len(style) + 8)  → ' style=".."'
        # 클래스 전환 비용: n * (len(cls) + 9) + len(cls) + len(style) + 3
        inline_cost = n * (len(style) + 8)
        class_cost = n * (len(cls) + 9) + len(cls) + len(style) + 3
        if class_cost < inline_cost:
            names[style] = cls

    def swap(m: re.Match) -> str:
        style = m.group(2)
        cls = names.get(style)
        return f' class="{cls}"' if cls else m.group(0)

    body = STYLE_ATTR.sub(swap, html)
    rules = "".join(
        f".{cls}{{{style}}}"
        for style, cls in sorted(names.items(), key=lambda kv: kv[1])
    )
    return f"<style>{rules}</style>{body}"


def _name(i: int) -> str:
    """0,1,2… → a, b, …, z, aa, ab …"""
    out = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(97 + r) + out
    return out


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("사용법: python scripts/compact_html.py REPORT_JSON")
    data = json.loads(open(sys.argv[1], encoding="utf-8").read())
    before = len(data["html"])
    data["html"] = compact(data["html"])
    after = len(data["html"])
    print(f"{before:,}자 → {after:,}자 ({after/before*100:.0f}%)", file=sys.stderr)
    json.dump(data, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
