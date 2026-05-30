"""보유 종목 모니터링 유스케이스.

포트폴리오 파일(YAML/JSON)을 읽어 현재가 반영 평가손익·비중·집중도 등
정량 지표를 계산하고, 리스크 매니저 엔진으로 정성 가이드를 덧붙인다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..agents.engine import AnalysisEngine
from ..config import Config
from ..data.provider import MarketDataProvider, resolve_ticker
from ..domain import Holding, Market, PortfolioReview, Position


def load_portfolio(path: Path) -> tuple[list[Holding], str, float]:
    """포트폴리오 파일 로드 → (보유내역, 기준통화, 현금)."""
    text = path.read_text(encoding="utf-8")
    data: dict[str, Any]
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml

            data = yaml.safe_load(text) or {}
        except Exception as e:  # PyYAML 미설치
            raise RuntimeError(
                f"YAML 파싱 실패({e}). PyYAML 설치 또는 JSON 파일을 사용하세요."
            )
    else:
        data = json.loads(text)

    base_currency = str(data.get("base_currency", "KRW")).upper()
    cash = float(data.get("cash", 0) or 0)
    holdings: list[Holding] = []
    for h in data.get("holdings", []):
        holdings.append(
            Holding(
                raw_ticker=str(h["ticker"]),
                shares=float(h["shares"]),
                avg_price=float(h["avg_price"]),
            )
        )
    if not holdings:
        raise RuntimeError("포트폴리오에 holdings 항목이 없습니다.")
    return holdings, base_currency, cash


class MonitorService:
    def __init__(
        self,
        cfg: Config,
        provider: MarketDataProvider,
        engine: AnalysisEngine,
        log=print,
    ) -> None:
        self.cfg = cfg
        self.provider = provider
        self.engine = engine
        self.log = log

    def monitor(self, holdings: list[Holding], base_currency: str, cash: float) -> PortfolioReview:
        fx = self._safe_fx()
        review = PortfolioReview(base_currency=base_currency, fx_usdkrw=fx, cash_base=cash)

        for h in holdings:
            tk = resolve_ticker(h.raw_ticker)
            pos = Position(
                ticker=tk,
                currency=tk.market.currency,
                shares=h.shares,
                avg_price=h.avg_price,
            )
            try:
                self.log(f"[보유] {tk.display()} 현재가 조회...")
                data = self.provider.get_stock_data(tk)
                pos.ticker = data.ticker
                pos.current_price = data.price
                pos.sector = data.sector
            except Exception as e:
                review.errors.append(f"{tk.display()} 조회 실패: {e}")

            self._compute_position(pos, base_currency, fx)
            review.positions.append(pos)

        self._aggregate(review)

        self.log("[점검] 리스크 매니저 포트폴리오 종합 점검...")
        try:
            review = self.engine.review_portfolio(review)
        except Exception as e:
            review.errors.append(f"포트폴리오 점검 실패: {e}")
        return review

    # --------------------------------------------------------- 내부 계산
    def _safe_fx(self) -> float:
        try:
            return float(self.provider.get_fx_usdkrw())
        except Exception:
            return 1350.0

    def _compute_position(self, pos: Position, base: str, fx: float) -> None:
        pos.cost_basis = pos.shares * pos.avg_price
        if pos.current_price is not None:
            pos.market_value = pos.shares * pos.current_price
            pos.pnl = pos.market_value - pos.cost_basis
            pos.pnl_pct = (
                (pos.current_price / pos.avg_price - 1) * 100 if pos.avg_price else 0.0
            )
        else:
            pos.market_value = pos.cost_basis  # 현재가 없으면 매입가로 대체
        pos.value_base = self._to_base(pos.market_value, pos.currency, base, fx)

    @staticmethod
    def _to_base(amount: float, currency: str, base: str, fx: float) -> float:
        if currency == base:
            return amount
        if currency == "USD" and base == "KRW":
            return amount * fx
        if currency == "KRW" and base == "USD":
            return amount / fx if fx else amount
        return amount

    def _aggregate(self, review: PortfolioReview) -> None:
        total_value = sum(p.value_base for p in review.positions) + review.cash_base
        total_cost = sum(
            self._to_base(p.cost_basis, p.currency, review.base_currency, review.fx_usdkrw)
            for p in review.positions
        )
        review.total_value_base = total_value
        review.total_cost_base = total_cost + review.cash_base
        review.total_pnl_base = total_value - review.total_cost_base
        review.total_pnl_pct = (
            (review.total_pnl_base / review.total_cost_base * 100)
            if review.total_cost_base
            else 0.0
        )

        denom = total_value or 1.0
        sector_w: dict[str, float] = {}
        market_w: dict[str, float] = {}
        for p in review.positions:
            p.weight_pct = p.value_base / denom * 100
            sec = p.sector or "기타"
            sector_w[sec] = sector_w.get(sec, 0.0) + p.weight_pct
            mk = p.ticker.market.value
            market_w[mk] = market_w.get(mk, 0.0) + p.weight_pct
        if review.cash_base:
            market_w["현금"] = review.cash_base / denom * 100
        review.sector_weights = {k: round(v, 1) for k, v in sorted(
            sector_w.items(), key=lambda kv: kv[1], reverse=True
        )}
        review.market_weights = {k: round(v, 1) for k, v in sorted(
            market_w.items(), key=lambda kv: kv[1], reverse=True
        )}
