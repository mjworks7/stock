"""LLM 입력용 컨텍스트 포매팅 — 정량 데이터를 읽기 좋은 텍스트로 변환."""
from __future__ import annotations

from ..domain import MacroSnapshot, StockData


def _fmt(v, unit: str = "") -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:,.2f}{unit}"
    return f"{v}{unit}"


def format_stock(data: StockData) -> str:
    t = data.ticker
    cur = data.currency
    lines = [
        f"종목: {t.name or t.raw} ({t.raw}) / 시장: {t.market.value} / 통화: {cur}",
        f"섹터: {data.sector or 'N/A'} | 산업: {data.industry or 'N/A'}",
        f"현재가: {_fmt(data.price)} | 시가총액: {_fmt(data.market_cap)}",
        "--- 밸류에이션 ---",
        f"PER(TTM): {_fmt(data.per)} | 선행PER: {_fmt(data.forward_per)} | PBR: {_fmt(data.pbr)} "
        f"| PSR: {_fmt(data.psr)} | EV/EBITDA: {_fmt(data.ev_ebitda)} | 배당수익률: {_fmt(data.dividend_yield)}",
        "--- 성장성/수익성 ---",
        f"매출성장(YoY): {_fmt(data.revenue_growth, '%')} | 이익성장(YoY): {_fmt(data.earnings_growth, '%')}",
        f"영업이익률: {_fmt(data.operating_margin, '%')} | 순이익률: {_fmt(data.profit_margin, '%')} "
        f"| ROE: {_fmt(data.roe, '%')}",
        "--- 재무건전성 ---",
        f"부채비율(D/E): {_fmt(data.debt_to_equity)} | 유동비율: {_fmt(data.current_ratio)} "
        f"| FCF: {_fmt(data.free_cashflow)}",
        "--- 가격/모멘텀 ---",
        f"52주 고가: {_fmt(data.week52_high)} | 52주 저가: {_fmt(data.week52_low)} "
        f"| MA50: {_fmt(data.ma50)} | MA200: {_fmt(data.ma200)} | 베타: {_fmt(data.beta)}",
        f"수익률 1M/3M/6M/1Y: {_fmt(data.ret_1m,'%')} / {_fmt(data.ret_3m,'%')} / "
        f"{_fmt(data.ret_6m,'%')} / {_fmt(data.ret_1y,'%')}",
    ]
    if data.warnings:
        lines.append("--- 데이터 경고 ---")
        lines.extend(f"- {w}" for w in data.warnings)
    return "\n".join(lines)


def format_macro(macro: MacroSnapshot) -> str:
    mkt = macro.market.value if macro.market else "-"
    lines = [f"거시 스냅샷 ({macro.as_of}, 시장={mkt})"]
    for k, v in macro.indicators.items():
        if isinstance(v, dict):
            lvl = v.get("level")
            chg = v.get("change_3m_pct")
            lines.append(f"- {k}: 수준={_fmt(lvl)}, 3개월변화={_fmt(chg, '%')}")
        else:
            lines.append(f"- {k}: {v}")
    for n in macro.notes:
        lines.append(f"  · {n}")
    return "\n".join(lines)
