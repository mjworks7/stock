"""오케스트레이션 유스케이스 — 데이터 수집 → 전문가 분석 → 종합 → 순위.

project-orchestration-manager 의 역할을 코드로 구현한 부분.
각 종목에 대해 전문가 에이전트를 순서대로 호출하고 결과를 종합한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..agents.engine import AnalysisEngine
from ..config import Config
from ..data.provider import MarketDataProvider, resolve_ticker
from ..domain import (
    AnalystOpinion,
    MacroSnapshot,
    Market,
    RankingEntry,
    StockData,
    StockVerdict,
)


@dataclass
class AnalysisResult:
    verdicts: list[StockVerdict] = field(default_factory=list)
    ranking: list[RankingEntry] = field(default_factory=list)
    ranking_summary: str = ""
    macro: dict[str, MacroSnapshot] = field(default_factory=dict)  # market -> snapshot
    macro_opinions: dict[str, AnalystOpinion] = field(default_factory=dict)
    engine_kind: str = ""
    errors: list[str] = field(default_factory=list)


class AdvisorService:
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

    def analyze(self, raw_tickers: list[str]) -> AnalysisResult:
        result = AnalysisResult(engine_kind=type(self.engine).__name__)
        tickers = [resolve_ticker(r) for r in raw_tickers if r.strip()]

        # 1) 시장별 거시 분석 (시장당 1회, 캐시)
        macro_op_cache: dict[Market, AnalystOpinion] = {}
        for market in {t.market for t in tickers}:
            self.log(f"[거시] {market.value} 시장 국면 분석 중...")
            snap = self.provider.get_macro(market)
            result.macro[market.value] = snap
            op = self.engine.analyze_macro(snap)
            macro_op_cache[market] = op
            result.macro_opinions[market.value] = op

        # 2) 종목별 파이프라인
        for tk in tickers:
            try:
                self.log(f"[데이터] {tk.display()} 시세/재무 수집 중...")
                data: StockData = self.provider.get_stock_data(tk)

                macro_op = macro_op_cache[tk.market]
                self.log(f"[섹터] {data.ticker.display()} 산업/섹터 분석...")
                sector_op = self.engine.analyze_sector(data, result.macro[tk.market.value])
                self.log(f"[펀더멘털] {data.ticker.display()} 기업 분석...")
                fund_op = self.engine.analyze_fundamental(data)
                self.log(f"[밸류에이션] {data.ticker.display()} 적정성 평가...")
                val_op = self.engine.analyze_valuation(data)

                self.log(f"[종합] {data.ticker.display()} 리스크 종합 판단...")
                verdict = self.engine.synthesize(
                    data, macro_op, [sector_op, fund_op, val_op]
                )
                result.verdicts.append(verdict)
            except Exception as e:  # 한 종목 실패가 전체를 막지 않도록
                msg = f"{tk.display()} 분석 실패: {e}"
                self.log(f"[오류] {msg}")
                result.errors.append(msg)

        # 3) 종목 간 추천 순위
        if result.verdicts:
            self.log("[순위] 종목 비교 및 추천 순위 산출...")
            entries, summary = self.engine.rank(result.verdicts)
            result.ranking = entries
            result.ranking_summary = summary

        return result
