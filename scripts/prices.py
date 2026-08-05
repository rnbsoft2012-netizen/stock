#!/usr/bin/env python3
"""
포트폴리오 시세/손익 조회 스크립트.

Yahoo Finance chart API에서 시세를 가져와 portfolio.yaml의 계좌별
보유수량/평단가와 합쳐 평가금액과 손익을 계산한다.
뉴스는 이 스크립트가 아니라 PlayMCP 네이버뉴스 검색으로 별도 조회한다.

yfinance 대신 requests를 직접 쓰는 이유: yfinance는 내부적으로 curl_cffi로
브라우저 TLS 지문을 위장하는데, 클라우드 세션의 보안 프록시가 그 연결을
리셋해버린다. 같은 Yahoo 엔드포인트를 평범한 requests로 호출하면 정상 동작한다.

pykrx를 쓰지 않는 이유: 최신 pykrx(1.2.8)는 KRX 계정(KRX_ID/KRX_PW) 로그인을
요구하는데, 클라우드 환경변수에는 안전한 비밀 저장소가 없어 계정 비밀번호를
두기에 적절하지 않다. Yahoo가 국내 종목도 원화로 제공하므로 한 소스로 통일했다.

사용법: python scripts/prices.py [portfolio.yaml 경로]
출력: JSON (stdout)
"""
import sys
import json
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
import requests

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
# 컨테이너는 UTC로 돈다. 아침 7시 KST는 UTC로 전날 22시이므로, 날짜 표기는
# 반드시 KST로 해야 브리핑에 하루 전 날짜가 찍히지 않는다.
KST = ZoneInfo("Asia/Seoul")


def today_kst() -> datetime.date:
    return datetime.datetime.now(KST).date()


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch_quote(session: requests.Session, ticker: str) -> dict:
    """Yahoo chart API에서 현재가/전일종가/52주 범위를 뽑아온다."""
    resp = session.get(
        CHART_URL.format(ticker=ticker),
        params={"range": "1mo", "interval": "1d"},
        timeout=20,
    )
    resp.raise_for_status()
    result = resp.json()["chart"]["result"][0]
    meta = result["meta"]

    # 일봉 시계열에서 전일 종가를 찾는다. 마지막 봉이 현재가와 같은 날이면
    # 그 앞 봉이 전일 종가, 아니면 마지막 봉 자체가 전일 종가다.
    timestamps = result.get("timestamp") or []
    raw_closes = result["indicators"]["quote"][0].get("close") or []
    bars = [(ts, c) for ts, c in zip(timestamps, raw_closes) if c is not None]

    current_price = meta.get("regularMarketPrice")
    if current_price is None and bars:
        current_price = bars[-1][1]

    # 날짜 비교는 거래소 현지시간 기준으로 한다. UTC로 비교하면 장 시간이
    # UTC 자정을 넘는 거래소에서 마지막 봉을 하루 밀리게 읽는다.
    offset = datetime.timedelta(seconds=meta.get("gmtoffset") or 0)

    def exchange_date(epoch: int) -> datetime.date:
        return (datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc) + offset).date()

    prev_close = None
    if bars:
        market_time = meta.get("regularMarketTime")
        market_date = exchange_date(market_time) if market_time else None
        last_bar_date = exchange_date(bars[-1][0])
        if market_date is not None and last_bar_date == market_date:
            prev_close = bars[-2][1] if len(bars) >= 2 else None
        else:
            prev_close = bars[-1][1]

    day_change_pct = None
    if current_price is not None and prev_close:
        day_change_pct = round((current_price - prev_close) / prev_close * 100, 2)

    week52_low = meta.get("fiftyTwoWeekLow")
    return {
        "current_price": current_price,
        "day_change_pct": day_change_pct,
        "currency": meta.get("currency"),
        "week52_high": meta.get("fiftyTwoWeekHigh"),
        # Yahoo가 국내 종목에 0을 주는 경우가 있어 걸러낸다
        "week52_low": week52_low if week52_low else None,
        "yahoo_name": meta.get("shortName") or meta.get("longName"),
    }


def with_pnl(holding: dict, quote: dict) -> dict:
    """보유수량/평단가와 시세를 합쳐 평가금액과 손익을 계산한다."""
    row = {
        "name": holding["name"],
        "code": holding.get("code"),
        "ticker": holding["ticker"],
        "news_query": holding.get("news_query", holding["name"]),
        "quantity": holding["quantity"],
        "avg_price": holding["avg_price"],
        **quote,
    }
    price = quote["current_price"]
    if price is not None:
        valuation = price * holding["quantity"]
        cost = holding["avg_price"] * holding["quantity"]
        row["valuation"] = round(valuation)
        row["cost"] = round(cost)
        row["profit_loss"] = round(valuation - cost)
        row["profit_loss_pct"] = round((valuation - cost) / cost * 100, 2) if cost else None
    return row


def summarize(rows: list) -> dict:
    """평가금액이 계산된 행들의 합계."""
    priced = [r for r in rows if r.get("valuation") is not None]
    valuation = sum(r["valuation"] for r in priced)
    cost = sum(r["cost"] for r in priced)
    # 전일 종가 기준 평가금액과 비교해 하루 등락을 낸다
    prev_valuation = sum(
        r["valuation"] / (1 + r["day_change_pct"] / 100)
        for r in priced
        if r.get("day_change_pct") is not None
    )
    covered = sum(r["valuation"] for r in priced if r.get("day_change_pct") is not None)
    return {
        "valuation": round(valuation),
        "cost": round(cost),
        "profit_loss": round(valuation - cost),
        "profit_loss_pct": round((valuation - cost) / cost * 100, 2) if cost else None,
        "day_change_pct": (
            round((covered - prev_valuation) / prev_valuation * 100, 2)
            if prev_valuation
            else None
        ),
    }


def main():
    portfolio_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parent.parent / "portfolio.yaml"
    )
    with open(portfolio_path, "r", encoding="utf-8") as f:
        portfolio = yaml.safe_load(f)

    session = make_session()
    accounts = portfolio.get("accounts", [])

    # 같은 종목을 여러 계좌가 들고 있을 수 있으므로 티커당 한 번만 조회한다
    quotes = {}
    for account in accounts:
        for holding in account.get("holdings", []):
            ticker = holding["ticker"]
            if ticker in quotes:
                continue
            try:
                quotes[ticker] = fetch_quote(session, ticker)
            except Exception as exc:
                quotes[ticker] = {
                    "current_price": None,
                    "day_change_pct": None,
                    "currency": None,
                    "week52_high": None,
                    "week52_low": None,
                    "yahoo_name": None,
                    "error": str(exc),
                }

    output = {"date": today_kst().isoformat(), "accounts": []}
    all_rows = []
    for account in accounts:
        rows = [with_pnl(h, quotes[h["ticker"]]) for h in account.get("holdings", [])]
        all_rows.extend(rows)
        output["accounts"].append(
            {
                "id": account.get("id"),
                "name": account.get("name"),
                "summary": summarize(rows),
                "holdings": rows,
            }
        )

    # 여러 계좌에 걸친 같은 종목은 하나로 합산한 관점도 제공한다
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
                "day_change_pct": row["day_change_pct"],
                "current_price": row["current_price"],
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

    output["combined"] = {
        "summary": summarize(all_rows),
        "holdings": sorted(merged.values(), key=lambda e: -e["valuation"]),
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
