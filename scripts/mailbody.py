#!/usr/bin/env python3
"""
카톡 브리핑과 같은 내용을 메일 본문(제목/평문/HTML)으로 만든다.

카톡은 1건당 200자라 전 종목을 못 싣지만 메일은 제한이 없다. 그래서 메일에는
주목 종목 5개 + **전 종목 표**를 함께 넣는다.

뉴스 헤드라인과 전략 문장은 이 스크립트가 만들지 않는다. 카톡용으로 이미 쓴
것을 그대로 재사용한다 — 두 경로가 다른 말을 하면 안 되기 때문이다.

사용법:
    python scripts/mailbody.py NOTES_FILE [BRIEFING_JSON]

NOTES_FILE은 티커를 키로 하는 JSON:
    {"347850.KQ": {"news": "...", "strategy": "..."}, ...}

BRIEFING_JSON은 `python scripts/brief.py`의 출력을 저장한 파일이다. **반드시
넘길 것.** 생략하면 시세를 새로 조회하는데, 장중에 실행하면 카톡으로 이미
보낸 숫자와 메일 숫자가 어긋나고 주목 종목 5개도 달라진다. 같은 아침의 카톡과
메일은 같은 실행 결과를 써야 한다.

출력: JSON {"subject": ..., "text": ..., "html": ...}
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brief import build_briefing, fmt_pct, fmt_won  # noqa: E402

DISCLAIMER = "* 투자 참고용이며 투자 권유가 아닙니다."


def build(notes: dict, briefing: dict | None = None) -> dict:
    briefing = briefing or build_briefing()
    date = briefing["date"]
    subject = f"[주식 브리핑] {date}"

    lines = [briefing["summary_message"], ""]
    html = [
        f"<h2>주식 브리핑 {date}</h2>",
        "<pre style='font-family:inherit;font-size:15px'>"
        + briefing["summary_message"]
        + "</pre>",
        "<h3>주목 종목</h3>",
    ]

    lines.append("[주목 종목]")
    for item in briefing["notable"]:
        note = notes.get(item["ticker"], {})
        block = [item["stat_line"]]
        if note.get("news"):
            block.append(f"뉴스: {note['news']}")
        if note.get("strategy"):
            block.append(f"전략: {note['strategy']}")
        lines.append("")
        lines.append("\n".join(block))
        html.append(
            "<pre style='font-family:inherit;font-size:15px;"
            "border-left:3px solid #ddd;padding-left:10px'>"
            + "\n".join(block)
            + "</pre>"
        )

    lines += ["", "[전 종목]", ""]
    header = f"{'종목':<14}{'현재가':>12}{'당일':>8}{'평가손익':>13}{'수익률':>9}{'비중':>7}{'52주고점':>9}"
    lines.append(header)
    html.append("<h3>전 종목</h3>")
    html.append(
        "<table cellpadding='6' style='border-collapse:collapse;font-size:14px'>"
        "<tr style='background:#f2f2f2'>"
        "<th align='left'>종목</th><th align='right'>현재가</th><th align='right'>당일</th>"
        "<th align='right'>평가손익</th><th align='right'>수익률</th>"
        "<th align='right'>비중</th><th align='right'>52주고점</th></tr>"
    )
    for row in briefing["all_holdings"]:
        high = row.get("vs_52w_high_pct")
        cells = [
            row["name"],
            f"{row['current_price']:,.0f}",
            fmt_pct(row["day_change_pct"]),
            fmt_won(row["profit_loss"]),
            fmt_pct(row["profit_loss_pct"]),
            f"{row['weight_pct']}%" if row["weight_pct"] is not None else "-",
            f"{high:+.1f}%" if high is not None else "-",
        ]
        lines.append(
            f"{cells[0]:<14}{cells[1]:>12}{cells[2]:>8}{cells[3]:>13}"
            f"{cells[4]:>9}{cells[5]:>7}{cells[6]:>9}"
        )
        # 손실은 눈에 띄어야 한다. 색은 수익률 기준으로만 준다.
        color = "#c0392b" if (row.get("profit_loss") or 0) < 0 else "#27ae60"
        html.append(
            "<tr>"
            f"<td>{cells[0]}</td><td align='right'>{cells[1]}</td>"
            f"<td align='right'>{cells[2]}</td>"
            f"<td align='right' style='color:{color}'>{cells[3]}</td>"
            f"<td align='right' style='color:{color}'>{cells[4]}</td>"
            f"<td align='right'>{cells[5]}</td><td align='right'>{cells[6]}</td></tr>"
        )
    html.append("</table>")

    lines += ["", DISCLAIMER]
    html.append(f"<p style='color:#888;font-size:13px'>{DISCLAIMER}</p>")

    return {"subject": subject, "text": "\n".join(lines), "html": "\n".join(html)}


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    notes = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    briefing = None
    if len(sys.argv) > 2:
        briefing = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    print(json.dumps(build(notes, briefing), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
