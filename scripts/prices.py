#!/usr/bin/env python3
"""
포트폴리오 시세/손익 조회 스크립트.

국내(.KS/.KQ)와 해외 종목 모두 Yahoo Finance chart API에서 시세를 가져와
portfolio.yaml의 보유수량/평단가와 합쳐 평가금액과 손익을 계산한다.
해외 종목은 Yahoo 뉴스 헤드라인도 함께 담는다
(국내 종목 뉴스는 PlayMCP 네이버뉴스 검색으로 별도 조회한다).

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

import yaml
import requests

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


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

    # 일봉 시계열에서 전일 종가를 찾는다. 마지막 봉이 오늘(=현재가와 같은 날)이면
    # 그 앞 봉이 전일 종가, 아니면 마지막 봉 자체가 전일 종가다.
    timestamps = result.get("timestamp") or []
    raw_closes = result["indicators"]["quote"][0].get("close") or []
    bars = [
        (ts, close)
        for ts, close in zip(timestamps, raw_closes)
        if close is not None
    ]

    current_price = meta.get("regularMarketPrice")
    if current_price is None and bars:
        current_price = bars[-1][1]

    prev_close = None
    if bars:
        market_time = meta.get("regularMarketTime")
        market_date = (
            datetime.datetime.utcfromtimestamp(market_time).date()
            if market_time
            else None
        )
        last_bar_date = datetime.datetime.utcfromtimestamp(bars[-1][0]).date()
        if market_date is not None and last_bar_date == market_date:
            prev_close = bars[-2][1] if len(bars) >= 2 else None
        else:
            prev_close = bars[-1][1]

    day_change_pct = None
    if current_price is not None and prev_close:
        day_change_pct = round((current_price - prev_close) / prev_close * 100, 2)

    return {
        "current_price": current_price,
        "day_change_pct": day_change_pct,
        "currency": meta.get("currency"),
        "week52_high": meta.get("fiftyTwoWeekHigh"),
        "week52_low": meta.get("fiftyTwoWeekLow"),
    }


def fetch_news(session: requests.Session, ticker: str, count: int = 3) -> list:
    """해외 종목용 Yahoo 뉴스 헤드라인."""
    try:
        resp = session.get(
            SEARCH_URL,
            params={"q": ticker, "newsCount": count, "quotesCount": 0},
            timeout=20,
        )
        resp.raise_for_status()
        return [
            {
                "title": n.get("title"),
                "publisher": n.get("publisher"),
                "link": n.get("link"),
            }
            for n in resp.json().get("news", [])[:count]
            if n.get("title")
        ]
    except Exception:
        return []


def with_pnl(item: dict, quote: dict) -> dict:
    """보유수량/평단가와 시세를 합쳐 평가금액과 손익을 계산한다."""
    row = {
        "name": item["name"],
        "ticker": item["ticker"],
        "quantity": item["quantity"],
        "avg_price": item["avg_price"],
        **quote,
    }
    for optional in ("code", "news_query"):
        if item.get(optional):
            row[optional] = item[optional]

    price = quote["current_price"]
    if price is not None:
        valuation = price * item["quantity"]
        cost = item["avg_price"] * item["quantity"]
        row["valuation"] = round(valuation, 2)
        row["profit_loss"] = round(valuation - cost, 2)
        row["profit_loss_pct"] = round((valuation - cost) / cost * 100, 2) if cost else None
    return row


def main():
    portfolio_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parent.parent / "portfolio.yaml"
    )
    with open(portfolio_path, "r", encoding="utf-8") as f:
        portfolio = yaml.safe_load(f)

    session = make_session()
    output = {"date": datetime.date.today().isoformat(), "domestic": [], "overseas": []}

    for item in portfolio.get("domestic", []):
        try:
            output["domestic"].append(with_pnl(item, fetch_quote(session, item["ticker"])))
        except Exception as exc:
            output["domestic"].append({"name": item["name"], "ticker": item["ticker"], "error": str(exc)})

    for item in portfolio.get("overseas", []):
        try:
            row = with_pnl(item, fetch_quote(session, item["ticker"]))
            row["news"] = fetch_news(session, item["ticker"])
            output["overseas"].append(row)
        except Exception as exc:
            output["overseas"].append({"name": item["name"], "ticker": item["ticker"], "error": str(exc)})

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
