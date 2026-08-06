#!/usr/bin/env python3
"""
전 종목 카드형 메일 리포트를 만든다.

카톡은 200자 제한 때문에 주목 종목 5개만 다루지만, 메일에는 **보유 23종목
전부**를 종목당 카드 하나로 싣는다. 카드 구성은 사용자가 지정한 형식이다:

    종목명 / 티커          현재가 · 당일등락 · 평가액
    목표가 | ×0.7 매수선 | 상태 배지
    계좌별 보유 (같은 종목을 A·B가 함께 들고 있으면 나눠서)
    【강세론】 … 【약세론】 …
    ▶ 대응  … / ✓ 체크 …

목표가·강세론·약세론·대응·체크는 이 스크립트가 만들지 않는다. 뉴스를 읽은
Claude가 NOTES 파일로 넘긴다. **목표가는 출처가 있을 때만 채운다** —
근거 없는 목표가를 지어내면 리포트 전체의 신뢰가 무너지므로, 확인되지 않으면
비워두고 카드에 "컨센서스 확인 안 됨"으로 표시한다.

사용법:
    python scripts/report.py NOTES_FILE [BRIEFING_JSON]

NOTES_FILE:
    {"005930.KS": {
        "target_low": 400000, "target_high": 440000,
        "target_source": "KB증권 53만원 상향(5/28), 평균 컨센 428,076원",
        "bull": "…", "bear": "…", "action": "…", "check": "…"}, ...}

BRIEFING_JSON은 `python scripts/brief.py`의 출력. 반드시 넘긴다(같은 아침의
카톡과 숫자가 어긋나지 않도록).

출력: JSON {"subject": ..., "html": ...}
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brief import build_briefing, fmt_pct, fmt_won  # noqa: E402

DISCLAIMER = "* 투자 참고용이며 투자 권유가 아닙니다. 목표가는 출처가 확인된 것만 표기했습니다."
BUY_LINE_RATIO = 0.7  # 사용자 기준: 목표가 × 0.7 을 매수 검토선으로 본다

RED = "#c0392b"
GREEN = "#0f9d58"
MUTED = "#8a8f98"
BORDER = "#e3e6ea"


def won(n) -> str:
    return "-" if n is None else f"{n:,.0f}원"


def man(n) -> str:
    """40~44만원 처럼 만원 단위로 줄여 쓴다."""
    return "-" if n is None else f"{n/10000:,.0f}만원"


def range_man(lo, hi) -> str:
    if lo is None and hi is None:
        return None
    if lo is None or hi is None:
        return man(lo if lo is not None else hi)
    if lo == hi:
        return man(lo)
    return f"{lo/10000:,.0f}~{hi/10000:,.0f}만원"


def pos_color(v) -> str:
    return GREEN if (v or 0) >= 0 else RED


def account_rows(row: dict, price) -> str:
    """계좌별 보유. 두 계좌에 걸친 종목은 평단이 크게 다르므로 반드시 나눈다."""
    accounts = row.get("accounts") or []
    if not accounts:
        return ""
    multi = len(accounts) > 1
    cells = []
    for a in accounts:
        val = price * a["quantity"] if price is not None else None
        cells.append(
            f"<tr>"
            f"<td style='padding:3px 10px 3px 0;color:{MUTED}'>{a['account']}</td>"
            f"<td style='padding:3px 10px 3px 0'>{a['quantity']:,}주</td>"
            f"<td style='padding:3px 10px 3px 0'>평단 {a['avg_price']:,.0f}원</td>"
            f"<td style='padding:3px 10px 3px 0;color:{pos_color(a.get('profit_loss_pct'))}'>"
            f"{fmt_pct(a.get('profit_loss_pct'))}</td>"
            f"<td style='padding:3px 0;color:{MUTED}'>{won(val)}</td>"
            f"</tr>"
        )
    title = "계좌별 (평단 차이 큼)" if multi else "계좌"
    return (
        f"<div style='margin:10px 0 0'>"
        f"<div style='font-size:12px;color:{MUTED};margin-bottom:3px'>{title}</div>"
        f"<table style='font-size:13px;border-collapse:collapse'>{''.join(cells)}</table>"
        f"</div>"
    )


def card(row: dict, note: dict) -> str:
    price = row.get("current_price")
    day = row.get("day_change_pct")
    arrow = "▲" if (day or 0) > 0 else ("▼" if (day or 0) < 0 else "―")
    lo, hi = note.get("target_low"), note.get("target_high")
    target = range_man(lo, hi)
    buy_lo = lo * BUY_LINE_RATIO if lo else None
    buy_hi = hi * BUY_LINE_RATIO if hi else None
    buy = range_man(buy_lo, buy_hi)
    multi = len(row.get("accounts") or []) > 1

    badges = [
        f"<span style='background:#eef1f5;color:#3c4450;border-radius:4px;"
        f"padding:2px 8px;font-size:12px'>보유</span>"
    ]
    if multi:
        badges.append(
            f"<span style='background:#fff4e5;color:#8a5a00;border-radius:4px;"
            f"padding:2px 8px;font-size:12px;margin-left:5px'>A·B 중복</span>"
        )

    head = (
        f"<table width='100%' style='border-collapse:collapse'><tr>"
        f"<td style='vertical-align:top'>"
        f"<div style='font-size:19px;font-weight:700'>{row['name']}</div>"
        f"<div style='font-size:12px;color:{MUTED};margin-top:2px'>{row['ticker']}</div>"
        f"</td>"
        f"<td align='right' style='vertical-align:top'>"
        f"<div style='font-size:19px;font-weight:700'>{won(price)}</div>"
        f"<div style='font-size:13px;color:{pos_color(day)};margin-top:2px'>"
        f"{arrow} {fmt_pct(day)}</div>"
        f"<div style='font-size:12px;color:{MUTED};margin-top:2px'>"
        f"평가 {won(row.get('valuation'))}</div>"
        f"</td></tr></table>"
    )

    if target:
        tgt_block = (
            f"<table style='border-collapse:collapse;font-size:13px'><tr>"
            f"<td style='padding-right:22px'>"
            f"<div style='color:{MUTED};font-size:12px'>목표가</div>"
            f"<div style='font-weight:700'>{target}</div></td>"
            f"<td style='padding-right:22px'>"
            f"<div style='color:{MUTED};font-size:12px'>×0.7 매수선</div>"
            f"<div style='font-weight:700'>{buy or '-'}</div></td>"
            f"<td>{''.join(badges)}</td>"
            f"</tr></table>"
        )
        if note.get("target_source"):
            tgt_block += (
                f"<div style='font-size:11px;color:{MUTED};margin-top:3px'>"
                f"출처: {note['target_source']}</div>"
            )
    else:
        tgt_block = (
            f"<table style='border-collapse:collapse;font-size:13px'><tr>"
            f"<td style='padding-right:22px'><div style='color:{MUTED};font-size:12px'>목표가</div>"
            f"<div style='color:{MUTED}'>컨센서스 확인 안 됨</div></td>"
            f"<td>{''.join(badges)}</td></tr></table>"
        )

    stats = (
        f"<div style='font-size:12px;color:{MUTED};margin-top:8px'>"
        f"수익률 <span style='color:{pos_color(row.get('profit_loss_pct'))}'>"
        f"{fmt_pct(row.get('profit_loss_pct'))}</span> "
        f"({fmt_won(row.get('profit_loss'))}) · 비중 {row.get('weight_pct')}% · "
        f"52주고점 {row.get('vs_52w_high_pct')}%</div>"
    )

    body = []
    if note.get("bull"):
        body.append(
            f"<div style='margin-top:10px;font-size:13px;line-height:1.65'>"
            f"<b style='color:{GREEN}'>【강세론】</b> {note['bull']}</div>"
        )
    if note.get("bear"):
        body.append(
            f"<div style='margin-top:4px;font-size:13px;line-height:1.65'>"
            f"<b style='color:{RED}'>【약세론】</b> {note['bear']}</div>"
        )
    if note.get("action"):
        body.append(
            f"<div style='margin-top:10px;padding:9px 11px;background:#f6f8fa;"
            f"border-radius:6px;font-size:13px;line-height:1.65'>"
            f"<b>▶ 대응</b> {note['action']}</div>"
        )
    if note.get("check"):
        body.append(
            f"<div style='margin-top:6px;font-size:12px;color:{MUTED}'>"
            f"✓ 체크: {note['check']}</div>"
        )

    return (
        f"<div style='border:1px solid {BORDER};border-radius:10px;padding:15px;"
        f"margin-bottom:13px'>"
        + head
        + f"<hr style='border:0;border-top:1px solid {BORDER};margin:11px 0'>"
        + tgt_block
        + stats
        + account_rows(row, price)
        + "".join(body)
        + "</div>"
    )


def build(notes: dict, briefing: dict | None = None) -> dict:
    briefing = briefing or build_briefing()
    date = briefing["date"]
    s = briefing["combined"]["summary"] if "combined" in briefing else None
    holdings = briefing["all_holdings"]

    summary = (
        f"<div style='border:1px solid {BORDER};border-radius:10px;padding:15px;"
        f"margin-bottom:16px;background:#fafbfc'>"
        f"<div style='font-size:13px;color:{MUTED}'>포트폴리오 합계</div>"
        f"<pre style='font-family:inherit;font-size:14px;margin:6px 0 0'>"
        f"{briefing['summary_message']}</pre></div>"
    )

    cards = [card(row, notes.get(row["ticker"], {})) for row in holdings]

    html = (
        f"<div style='font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\","
        f"Roboto,\"Apple SD Gothic Neo\",sans-serif;max-width:720px;color:#1c1f23'>"
        f"<h2 style='margin:0 0 4px'>보유주 — 대응 전략</h2>"
        f"<div style='font-size:13px;color:{MUTED};margin-bottom:16px'>"
        f"{date} · 보유 {len(holdings)}종목 · 조회 시점 시세 기준</div>"
        + summary
        + "".join(cards)
        + f"<p style='color:{MUTED};font-size:12px;margin-top:18px'>{DISCLAIMER}</p>"
        f"</div>"
    )
    return {"subject": f"[보유주 대응 전략] {date}", "html": html}


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
