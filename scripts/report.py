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
    python scripts/report.py NOTES_FILE [BRIEFING_JSON] [TECH_JSON]

TECH_JSON은 `python scripts/technical.py`의 출력. 넘기면 카드마다 추세·상대강도·
위치·변동성 블록과 스탠스가 붙고, 맨 위에 포트폴리오 구조 경고가 추가된다.

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


TREND_KR = {"up": "상승", "down": "하락", "side": "횡보", "unknown": "판정 불가"}
TREND_COLOR = {"up": GREEN, "down": RED, "side": "#8a6d00", "unknown": MUTED}


def tech_line(t: dict) -> str:
    """지표는 카드의 주인공이 아니라 "▶ 대응"의 근거다. 그래서 한 줄로 줄인다.

    상대강도(RS)를 빼지 않는 이유: 지수가 4% 빠지는 날에는 거의 모든 종목이
    내린다. 종목 자체의 문제인지 시장 탓인지는 RS로만 갈린다.
    """
    if not t or t.get("error"):
        return ""
    trend = t.get("trend", "unknown")
    rs6 = t.get("rs_6m_pct")
    rs = "-" if rs6 is None else (
        f"<span style='color:{GREEN if rs6 >= 0 else RED}'>{rs6:+.1f}%p</span>"
    )
    return (
        f"<div style='font-size:12px;color:#3c4450;margin-top:7px'>"
        f"<b style='color:{TREND_COLOR[trend]}'>추세 {TREND_KR[trend]}</b>"
        f" · 지수 대비 6M {rs}"
        f" · 52주 위치 {t.get('pos_52w_pct')}%"
        f" · RSI {t.get('rsi14')}"
        f" · 60일 {t.get('swing_low_60d'):,}~{t.get('swing_high_60d'):,}"
        f" · 연변동성 {t.get('vol_annual_pct')}%</div>"
    )


# 카드마다 되풀이하면 23번 읽어야 하는 규칙이라 맨 위에 한 번만 둔다.
LEGEND = (
    f"<div style='font-size:12px;color:{MUTED};line-height:1.75;margin-bottom:14px'>"
    f"<b>읽는 법</b> — <b>추가매수 ○</b> 진입 구간 있음 / <b>△</b> 지지 확인 후 소량 / "
    f"<b>✕</b> 신규 자금 넣지 않음. 매수 구간은 <b>증권사 목표가×0.7</b>과 "
    f"<b>MA60·60일 지지선</b>이 둘 다 허락할 때만 제시했고, 들어갈 때는 "
    f"한 번에 담지 말고 2~3회로 나눈다. 비중 상한은 종목의 연변동성으로 정한다"
    f"(변동성이 클수록 낮게). <b>여기 숫자는 전망이 아니라 이미 시장에 찍힌 값</b>이다."
    f"</div>"
)


def todo(holdings: list, plans: dict) -> str:
    """23장을 다 읽기 전에, 오늘 실제로 손볼 게 있는 종목만 먼저 보여준다.

    `plan.py`가 `kakao`를 채운 종목이 곧 그 대상이다 — 비중 상한 초과, 지지선
    이탈, 목표가 도달, 매수 구간 진입. 카톡으로 나가는 것과 같은 목록이라
    메일과 카톡이 어긋나지 않는다.
    """
    items = [
        (row, plans.get(row["ticker"]) or {})
        for row in holdings
        if (plans.get(row["ticker"]) or {}).get("kakao")
    ]
    if not items:
        return (
            f"<div style='border:1px solid {BORDER};border-radius:8px;padding:13px;"
            f"margin-bottom:16px;font-size:13px;color:{MUTED}'>"
            f"오늘 새로 결정할 종목 없음 — 지지선만 지켜보면 된다.</div>"
        )
    items.sort(key=lambda x: -(x[0].get("weight_pct") or 0))
    rows = "".join(
        f"<tr><td style='padding:4px 12px 4px 0;font-weight:700;white-space:nowrap'>"
        f"{row['name']}</td>"
        f"<td style='padding:4px 12px 4px 0;color:{MUTED};white-space:nowrap'>"
        f"비중 {row.get('weight_pct')}%</td>"
        f"<td style='padding:4px 0'>{p['kakao']}</td></tr>"
        for row, p in items
    )
    return (
        f"<div style='border:1px solid #d8e2f0;border-left:4px solid #1a5fb4;"
        f"border-radius:8px;padding:14px;margin-bottom:16px;background:#f7fafd'>"
        f"<div style='font-weight:700;margin-bottom:7px'>오늘 결정할 것 "
        f"({len(items)}종목)</div>"
        f"<table style='font-size:13px;border-collapse:collapse'>{rows}</table>"
        f"<div style='font-size:11px;color:{MUTED};margin-top:7px'>"
        f"나머지 종목은 아래 카드의 ▶ 대응에 기준선만 적어 뒀다 — 오늘 움직일 이유는 없다.</div>"
        f"</div>"
    )


def portfolio_risk(holdings: list, tech: dict) -> str:
    """종목별 카드보다 먼저 봐야 하는 것: 집중도와 추세 분포."""
    if not tech:
        return ""
    by_trend = {"up": [], "down": [], "side": [], "unknown": []}
    weak = []
    for row in holdings:
        t = tech.get(row["ticker"]) or {}
        trend = t.get("trend", "unknown")
        by_trend.setdefault(trend, []).append(row)
        if trend == "down" and (t.get("rs_6m_pct") or 0) < 0:
            weak.append(row)

    def wsum(rows):
        return round(sum(r.get("weight_pct") or 0 for r in rows), 1)

    top = max(holdings, key=lambda r: r.get("weight_pct") or 0)
    top_t = tech.get(top["ticker"]) or {}
    lines = [
        f"1위 종목 <b>{top['name']} {top['weight_pct']}%</b> — 연변동성 "
        f"{top_t.get('vol_annual_pct')}%, 1년 최대낙폭 {top_t.get('max_drawdown_1y_pct')}%. "
        f"포트폴리오 전체 등락의 상당 부분이 이 한 종목에서 나온다.",
        f"추세 분포 — 상승 {len(by_trend['up'])} / 횡보 {len(by_trend['side'])} / "
        f"하락 {len(by_trend['down'])}종목 (하락 추세 비중 합 {wsum(by_trend['down'])}%)",
        f"추세·상대강도 모두 약한 종목 {len(weak)}개, 비중 합 {wsum(weak)}% — "
        f"물타기가 아니라 비중 관리로 접근할 구간: "
        + ", ".join(r["name"] for r in sorted(weak, key=lambda r: -(r["weight_pct"] or 0))),
    ]
    return (
        f"<div style='border:1px solid {BORDER};border-left:4px solid {RED};"
        f"border-radius:8px;padding:14px;margin-bottom:16px;background:#fffbfb'>"
        f"<div style='font-weight:700;margin-bottom:7px'>먼저 볼 것 — 포트폴리오 구조</div>"
        f"<div style='font-size:13px;line-height:1.75'>"
        + "<br>".join(f"· {x}" for x in lines)
        + "</div></div>"
    )


def card(row: dict, note: dict, tech_row: dict | None = None,
         plan_row: dict | None = None) -> str:
    price = row.get("current_price")
    day = row.get("day_change_pct")
    arrow = "▲" if (day or 0) > 0 else ("▼" if (day or 0) < 0 else "―")
    lo, hi = note.get("target_low"), note.get("target_high")
    target = range_man(lo, hi)
    buy_lo = lo * BUY_LINE_RATIO if lo else None
    buy_hi = hi * BUY_LINE_RATIO if hi else None
    buy = range_man(buy_lo, buy_hi)
    multi = len(row.get("accounts") or []) > 1

    # 배지는 "지금 이 종목을 어떻게 할 것인가"를 한 단어로 — 카드를 훑을 때
    # 이 색만 보고도 손볼 종목이 골라져야 한다.
    badge_style = {
        "축소 검토": ("#fdecec", RED),
        "관찰": ("#fff4e5", "#8a5a00"),
        "보유": ("#e8f5ee", "#0b6b3a"),
    }
    label = (plan_row or {}).get("badge", "보유")
    bg, fg = badge_style.get(label, ("#eef1f5", "#3c4450"))
    badges = [
        f"<span style='background:{bg};color:{fg};border-radius:4px;"
        f"padding:2px 8px;font-size:12px'>{label}</span>"
    ]
    if multi:
        badges.append(
            f"<span style='background:#fff4e5;color:#8a5a00;border-radius:4px;"
            f"padding:2px 8px;font-size:12px;margin-left:5px'>A·B 중복</span>"
        )

    qty = sum(a["quantity"] for a in (row.get("accounts") or []))
    head = (
        f"<table width='100%' style='border-collapse:collapse'><tr>"
        f"<td style='vertical-align:top'>"
        f"<div style='font-size:19px;font-weight:700'>{row['name']}</div>"
        f"<div style='font-size:12px;color:{MUTED};margin-top:2px'>{row['ticker']}"
        f"{f' · {qty:,}주' if qty else ''}</div>"
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
    else:
        tgt_block = (
            f"<table style='border-collapse:collapse;font-size:13px'><tr>"
            f"<td style='padding-right:22px'><div style='color:{MUTED};font-size:12px'>목표가</div>"
            f"<div style='color:{MUTED}'>컨센서스 확인 안 됨</div></td>"
            f"<td>{''.join(badges)}</td></tr></table>"
        )
    # 출처 메모는 목표가가 **없을 때** 더 중요하다 — 왜 비웠는지(오래됐는지,
    # 커버리지가 없는지)를 알아야 "확인 안 됨"을 어떻게 받아들일지 정해진다.
    if note.get("target_source"):
        prefix = "출처: " if target else "메모: "
        tgt_block += (
            f"<div style='font-size:11px;color:{MUTED};margin-top:3px'>"
            f"{prefix}{note['target_source']}</div>"
        )

    stats = (
        f"<div style='font-size:12px;color:{MUTED};margin-top:8px'>"
        f"수익률 <span style='color:{pos_color(row.get('profit_loss_pct'))}'>"
        f"{fmt_pct(row.get('profit_loss_pct'))}</span> "
        f"({fmt_won(row.get('profit_loss'))}) · 비중 {row.get('weight_pct')}% · "
        f"52주고점 {row.get('vs_52w_high_pct')}%</div>"
    )

    # 강세론과 약세론은 한 덩어리로 붙인다. 따로 떼어 놓으면 둘 다 읽고 나서야
    # 균형이 잡히는데, 카드가 길어지면 앞의 한쪽만 읽고 넘어가게 된다.
    views = []
    if note.get("bull"):
        views.append(f"<b style='color:{GREEN}'>【강세론】</b>{note['bull']}")
    if note.get("bear"):
        views.append(f"<b style='color:{RED}'>【약세론】</b>{note['bear']}")
    body = []
    if views:
        body.append(
            f"<div style='margin-top:11px;font-size:13px;line-height:1.7'>"
            + " ".join(views)
            + "</div>"
        )

    # "▶ 대응"이 이 카드의 결론이다. plan.py가 만든 기준선이 먼저 오고,
    # 뉴스에서 읽은 종목별 사정(note.action)이 뒤에 붙는다.
    action_parts = list((plan_row or {}).get("lines") or [])
    if note.get("action"):
        action_parts.append(note["action"])
    if action_parts:
        stance = (plan_row or {}).get("stance")
        head_txt = f"<b style='color:{RED}'>▶ 대응</b>"
        if stance:
            head_txt += f" <b>{stance}</b>"
        body.append(
            f"<div style='margin-top:11px;padding:11px 12px;background:#f6f8fa;"
            f"border-left:3px solid {RED};border-radius:6px;font-size:13px;"
            f"line-height:1.75'>{head_txt}<br>"
            + "<br>".join(action_parts)
            + "</div>"
        )
    if note.get("check"):
        body.append(
            f"<div style='margin-top:7px;font-size:12px;color:{MUTED}'>"
            f"✓ 체크: {note['check']}</div>"
        )

    return (
        f"<div style='border:1px solid {BORDER};border-radius:10px;padding:15px;"
        f"margin-bottom:13px'>"
        + head
        + f"<hr style='border:0;border-top:1px solid {BORDER};margin:11px 0'>"
        + tgt_block
        + stats
        + tech_line(tech_row or {})
        + (account_rows(row, price) if multi else "")
        + "".join(body)
        + "</div>"
    )


def build(notes: dict, briefing: dict | None = None, tech: dict | None = None,
          plans: dict | None = None) -> dict:
    briefing = briefing or build_briefing()
    tech = tech or {}
    plans = plans or {}
    date = briefing["date"]
    holdings = briefing["all_holdings"]

    summary = (
        f"<div style='border:1px solid {BORDER};border-radius:10px;padding:15px;"
        f"margin-bottom:16px;background:#fafbfc'>"
        f"<div style='font-size:13px;color:{MUTED}'>포트폴리오 합계</div>"
        f"<pre style='font-family:inherit;font-size:14px;margin:6px 0 0'>"
        f"{briefing['summary_message']}</pre></div>"
    )

    cards = [
        card(row, notes.get(row["ticker"], {}), tech.get(row["ticker"]),
             plans.get(row["ticker"]))
        for row in holdings
    ]

    html = (
        f"<div style='font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\","
        f"Roboto,\"Apple SD Gothic Neo\",sans-serif;max-width:720px;color:#1c1f23'>"
        f"<h2 style='margin:0 0 4px'>보유주 — 대응 전략</h2>"
        f"<div style='font-size:13px;color:{MUTED};margin-bottom:16px'>"
        f"{date} · 보유 {len(holdings)}종목 · 조회 시점 시세 기준</div>"
        + summary
        + todo(holdings, plans)
        + portfolio_risk(holdings, tech)
        + LEGEND
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
    briefing = tech = None
    if len(sys.argv) > 2:
        briefing = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    if len(sys.argv) > 3:
        tech = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
    # 대응 기준선은 브리핑·지표가 둘 다 있을 때만 만들 수 있다.
    plans = None
    if briefing and tech:
        from plan import build_all  # noqa: PLC0415
        plans = build_all(briefing, tech, notes)
    print(json.dumps(build(notes, briefing, tech, plans), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
