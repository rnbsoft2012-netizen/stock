#!/usr/bin/env python3
"""
카톡 모닝 브리핑의 숫자 부분을 만들고, 상세히 다룰 "주목 종목"을 골라준다.

뉴스와 투자 코멘트는 이 스크립트가 만들지 않는다. 그건 매일 아침 Routine에서
Claude가 PlayMCP 네이버뉴스 검색 결과를 읽고 붙인다. 이 스크립트가 책임지는 건
숫자 계산, 종목 선별, 그리고 카톡 200자 제한을 넘지 않는 요약 메시지다.

사용법:
    python scripts/brief.py                 브리핑 재료를 JSON으로 출력
    python scripts/brief.py --check FILE    보낼 메시지들이 200자 이내인지 검증
                                            (FILE은 메시지 문자열 JSON 배열)
"""
import sys
import json
import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prices import fetch_quote, make_session, summarize, today_kst, with_pnl  # noqa: E402

KAKAO_LIMIT = 200
NOTABLE_BY_PCT = 3   # 등락률이 큰 순으로 뽑는 개수
NOTABLE_BY_WON = 2   # 그다음 하루 평가액 변동이 큰 순으로 더 뽑는 개수
WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def fmt_won(amount) -> str:
    """원 단위 금액을 억/만 단위로 짧게. 카톡 200자를 아끼기 위한 것."""
    if amount is None:
        return "-"
    sign = "-" if amount < 0 else ""
    man = round(abs(amount) / 10_000)
    eok, man = divmod(man, 10_000)
    if eok and man:
        return f"{sign}{eok}억{man:,}만"
    if eok:
        return f"{sign}{eok}억"
    return f"{sign}{man:,}만"


def fmt_pct(pct) -> str:
    return "-" if pct is None else f"{pct:+.2f}%"


def day_move_won(row: dict):
    """하루 동안 이 종목의 평가액이 움직인 금액."""
    pct = row.get("day_change_pct")
    if pct is None or row.get("valuation") is None or pct == -100:
        return None
    return row["valuation"] * pct / (100 + pct)


def pick_notable(holdings: list) -> list:
    """등락률이 큰 종목 + 평가액 변동이 큰 종목을 섞어 고른다.

    둘을 섞는 이유: 작은 종목의 -18%와 큰 종목의 +5%는 둘 다 알아야 한다.
    등락률만 보면 비중 큰 종목이 계속 빠지고, 금액만 보면 급등락을 놓친다.
    """
    priced = [h for h in holdings if h.get("day_change_pct") is not None]
    by_pct = sorted(priced, key=lambda h: -abs(h["day_change_pct"]))
    chosen = by_pct[:NOTABLE_BY_PCT]
    chosen_tickers = {h["ticker"] for h in chosen}

    rest = [h for h in priced if h["ticker"] not in chosen_tickers]
    by_won = sorted(rest, key=lambda h: -abs(day_move_won(h) or 0))
    chosen += by_won[:NOTABLE_BY_WON]
    return chosen


def build_summary_message(date: datetime.date, accounts: list, combined: dict) -> str:
    day = WEEKDAY_KR[date.weekday()]
    total = combined["summary"]
    lines = [
        f"[내 주식 브리핑] {date.month:02d}/{date.day:02d}({day})",
        f"평가 {fmt_won(total['valuation'])} (당일 {fmt_pct(total['day_change_pct'])})",
        f"손익 {fmt_won(total['profit_loss'])} ({fmt_pct(total['profit_loss_pct'])})",
    ]
    for account in accounts:
        s = account["summary"]
        lines.append(
            f"·{account['name']} {fmt_won(s['valuation'])} ({fmt_pct(s['profit_loss_pct'])})"
        )
    return "\n".join(lines)


def check_messages(path: str) -> int:
    messages = json.loads(Path(path).read_text(encoding="utf-8"))
    over = 0
    for i, message in enumerate(messages, 1):
        length = len(message)
        mark = "OK " if length <= KAKAO_LIMIT else "OVER"
        if length > KAKAO_LIMIT:
            over += 1
        print(f"{mark} [{i}/{len(messages)}] {length}자")
        if length > KAKAO_LIMIT:
            print(f"     {KAKAO_LIMIT}자 초과분: ...{message[KAKAO_LIMIT:]!r}")
    print(f"\n{len(messages)}건 중 {over}건이 {KAKAO_LIMIT}자를 넘습니다.")
    return 1 if over else 0


def build_briefing(portfolio_path: str | None = None) -> dict:
    """시세를 조회해 브리핑 재료(요약 메시지 + 주목 종목 + 전 종목)를 만든다."""
    root = Path(__file__).resolve().parent.parent
    path = Path(portfolio_path) if portfolio_path else root / "portfolio.yaml"
    portfolio = yaml.safe_load(path.read_text(encoding="utf-8"))
    session = make_session()

    quotes = {}
    for account in portfolio.get("accounts", []):
        for holding in account.get("holdings", []):
            if holding["ticker"] not in quotes:
                quotes[holding["ticker"]] = fetch_quote(session, holding["ticker"])

    accounts_out = []
    per_ticker_accounts = {}
    all_rows = []
    for account in portfolio.get("accounts", []):
        rows = [with_pnl(h, quotes[h["ticker"]]) for h in account.get("holdings", [])]
        all_rows.extend(rows)
        accounts_out.append({"name": account["name"], "summary": summarize(rows)})
        for row in rows:
            per_ticker_accounts.setdefault(row["ticker"], []).append(
                {
                    "account": account["name"],
                    "quantity": row["quantity"],
                    "avg_price": row["avg_price"],
                    "profit_loss_pct": row.get("profit_loss_pct"),
                }
            )

    merged = {}
    for row in all_rows:
        if row.get("valuation") is None:
            continue
        entry = merged.setdefault(
            row["ticker"],
            {
                "name": row["name"],
                "ticker": row["ticker"],
                "news_query": row["news_query"],
                "current_price": row["current_price"],
                "day_change_pct": row["day_change_pct"],
                "week52_high": row.get("week52_high"),
                "week52_low": row.get("week52_low"),
                "quantity": 0,
                "valuation": 0,
                "cost": 0,
            },
        )
        entry["quantity"] += row["quantity"]
        entry["valuation"] += row["valuation"]
        entry["cost"] += row["cost"]
    for entry in merged.values():
        entry["profit_loss"] = entry["valuation"] - entry["cost"]
        entry["profit_loss_pct"] = (
            round(entry["profit_loss"] / entry["cost"] * 100, 2) if entry["cost"] else None
        )
        entry["accounts"] = per_ticker_accounts[entry["ticker"]]

    holdings = sorted(merged.values(), key=lambda e: -e["valuation"])
    combined = {"summary": summarize(all_rows), "holdings": holdings}
    today = today_kst()

    notable = []
    for row in pick_notable(holdings):
        notable.append(
            {
                "name": row["name"],
                "ticker": row["ticker"],
                "news_query": row["news_query"],
                "day_change_pct": row["day_change_pct"],
                "stat_line": (
                    f"{row['name']} {row['current_price']:,.0f}원 "
                    f"({fmt_pct(row['day_change_pct'])})\n"
                    f"손익 {fmt_won(row['profit_loss'])}({fmt_pct(row['profit_loss_pct'])})"
                ),
                "held_in": row["accounts"],
                "week52_high": row["week52_high"],
                "week52_low": row["week52_low"],
            }
        )

    summary_message = build_summary_message(today, accounts_out, combined)
    return {
        "date": today.isoformat(),
        "summary_message": summary_message,
        "summary_message_len": len(summary_message),
        "kakao_limit": KAKAO_LIMIT,
        "notable": notable,
        "all_holdings": holdings,
    }


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--check":
        return check_messages(sys.argv[2])

    briefing = build_briefing(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps(briefing, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
