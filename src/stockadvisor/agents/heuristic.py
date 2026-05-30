"""휴리스틱(규칙기반) 분석 엔진 — 오프라인/무 API 키 환경용.

LLM 없이 정량 지표만으로 점수·판단을 산출한다. 정성적 토론은 없지만
파이프라인을 끝까지 돌려 리포트를 만들 수 있어 개발/테스트와
키 없는 사용자에게 유용하다.
"""
from __future__ import annotations

from ..config import Config
from ..domain import (
    AnalystOpinion,
    MacroSnapshot,
    PortfolioReview,
    RankingEntry,
    StockData,
    StockVerdict,
    TargetBand,
    TargetPrices,
)


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _stance(score: float) -> str:
    if score >= 60:
        return "bullish"
    if score <= 40:
        return "bearish"
    return "neutral"


class HeuristicEngine:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    # ----------------------------------------------------------- 개별 분석
    def analyze_macro(self, macro: MacroSnapshot) -> AnalystOpinion:
        score = 55.0
        points, risks = [], []
        vix = None
        for k, v in macro.indicators.items():
            if isinstance(v, dict) and "VIX" in k:
                vix = v.get("level")
        if vix is not None:
            if vix < 15:
                score += 10
                points.append(f"변동성(VIX {vix:.0f})이 낮아 위험선호 우호적")
            elif vix > 25:
                score -= 12
                risks.append(f"변동성(VIX {vix:.0f}) 상승 — 위험회피 국면 가능")
        return AnalystOpinion(
            analyst="macro-regime-analyst",
            role="거시·시장국면 분석가",
            stance=_stance(score),
            score=_clamp(score),
            confidence=0.4,
            summary="규칙기반 거시 점수(오프라인). 지표 수준으로 단순 산출.",
            key_points=points or ["뚜렷한 거시 신호 없음 — 중립 가정"],
            risks=risks,
        )

    def analyze_sector(self, data: StockData, macro: MacroSnapshot) -> AnalystOpinion:
        score = 50.0
        points, risks = [], []
        mom = data.ret_3m
        if mom is not None:
            score += _clamp(mom, -25, 25) * 0.8
            (points if mom >= 0 else risks).append(f"3개월 모멘텀 {mom:+.1f}%")
        if data.sector:
            points.append(f"섹터: {data.sector}")
        return AnalystOpinion(
            analyst="industry-sector-analyst",
            role="산업·섹터 분석가",
            stance=_stance(score),
            score=_clamp(score),
            confidence=0.4,
            summary="규칙기반 섹터 점수(오프라인). 모멘텀 위주 단순 산출.",
            key_points=points,
            risks=risks,
        )

    def analyze_fundamental(self, data: StockData) -> AnalystOpinion:
        score = 50.0
        points, risks = [], []
        if data.roe is not None:
            score += _clamp((data.roe - 8) * 1.2, -15, 20)
            points.append(f"ROE {data.roe:.1f}%")
        if data.operating_margin is not None:
            score += _clamp((data.operating_margin - 8) * 0.6, -10, 12)
            points.append(f"영업이익률 {data.operating_margin:.1f}%")
        if data.revenue_growth is not None:
            score += _clamp(data.revenue_growth * 0.5, -12, 15)
            (points if data.revenue_growth >= 0 else risks).append(
                f"매출성장 {data.revenue_growth:+.1f}%"
            )
        if data.debt_to_equity is not None and data.debt_to_equity > 150:
            score -= 10
            risks.append(f"높은 부채비율(D/E {data.debt_to_equity:.0f})")
        return AnalystOpinion(
            analyst="fundamental-analyst",
            role="펀더멘털 분석가",
            stance=_stance(score),
            score=_clamp(score),
            confidence=0.5,
            summary="규칙기반 펀더멘털 점수(오프라인).",
            key_points=points,
            risks=risks,
        )

    def analyze_valuation(self, data: StockData) -> AnalystOpinion:
        score = 50.0
        points, risks = [], []
        if data.per is not None and data.per > 0:
            # PER 낮을수록 매력적
            score += _clamp((20 - data.per) * 1.5, -25, 25)
            (points if data.per < 20 else risks).append(f"PER {data.per:.1f}")
        if data.pbr is not None and data.pbr > 0:
            score += _clamp((2.0 - data.pbr) * 8, -15, 15)
            (points if data.pbr < 2 else risks).append(f"PBR {data.pbr:.2f}")
        return AnalystOpinion(
            analyst="valuation-quant-analyst",
            role="밸류에이션·퀀트 분석가",
            stance=_stance(score),
            score=_clamp(score),
            confidence=0.5,
            summary="규칙기반 밸류에이션 점수(오프라인). 낮은 PER/PBR=높은 점수.",
            key_points=points,
            risks=risks,
        )

    # --------------------------------------------------------------- 종합
    def synthesize(
        self, data: StockData, macro_op: AnalystOpinion, opinions: list[AnalystOpinion]
    ) -> StockVerdict:
        w = self.cfg.weights or {}
        by_key = {o.analyst: o.score for o in [macro_op, *opinions]}
        macro_s = macro_op.score
        sector_s = by_key.get("industry-sector-analyst", 50)
        fund_s = by_key.get("fundamental-analyst", 50)
        val_s = by_key.get("valuation-quant-analyst", 50)
        tech_s = 50.0
        if data.ret_1m is not None:
            tech_s = _clamp(50 + data.ret_1m * 1.5)

        total = (
            macro_s * w.get("macro", 0.15)
            + sector_s * w.get("sector", 0.20)
            + fund_s * w.get("fundamental", 0.30)
            + val_s * w.get("valuation", 0.25)
            + tech_s * w.get("technical", 0.10)
        )
        total = _clamp(total)

        # 적정성: 밸류에이션 점수 기준
        if val_s >= 60:
            judgment = "저평가"
        elif val_s <= 40:
            judgment = "고평가"
        else:
            judgment = "적정"

        # 대응
        if total >= 70:
            action = "적극매수"
        elif total >= 58:
            action = "분할매수"
        elif total >= 45:
            action = "관망"
        elif total >= 35:
            action = "비중축소"
        else:
            action = "매도"

        price = data.price or 0.0
        # 점수 기반 기대 상승률 (보수적)
        upside = (total - 50) / 100.0  # -0.5 ~ +0.5
        st = TargetBand(
            horizon=self.cfg.horizons.get("short_term", "1-3개월"),
            low=round(price * (1 + upside * 0.3 - 0.05), 2),
            base=round(price * (1 + upside * 0.3), 2),
            high=round(price * (1 + upside * 0.3 + 0.05), 2),
            rationale="단기 모멘텀/종합점수 기반 추정(규칙기반).",
        )
        mt = TargetBand(
            horizon=self.cfg.horizons.get("mid_term", "6-12개월"),
            low=round(price * (1 + upside * 0.6 - 0.08), 2),
            base=round(price * (1 + upside * 0.6), 2),
            high=round(price * (1 + upside * 0.6 + 0.08), 2),
            rationale="중기 종합점수 기반 추정(규칙기반).",
        )
        lt = TargetBand(
            horizon=self.cfg.horizons.get("long_term", "1-3년"),
            low=round(price * (1 + upside * 1.0 - 0.12), 2),
            base=round(price * (1 + upside * 1.0), 2),
            high=round(price * (1 + upside * 1.0 + 0.15), 2),
            rationale="장기 종합점수 기반 추정(규칙기반).",
        )
        stop_pct = self.cfg.risk.get("default_stop_loss_pct", 10)
        stop_loss = round(price * (1 - stop_pct / 100.0), 2)
        pos = self.cfg.risk.get("max_position_pct", 20)
        pos = round(pos * (total / 100.0), 1)

        risks = [r for o in [macro_op, *opinions] for r in o.risks][:5]
        return StockVerdict(
            ticker=data.ticker,
            currency=data.currency,
            current_price=data.price,
            valuation_judgment=judgment,
            action=action,
            conviction=total,
            total_score=total,
            target_prices=TargetPrices(short_term=st, mid_term=mt, long_term=lt),
            stop_loss=stop_loss,
            suggested_position_pct=pos,
            thesis=(
                f"규칙기반 종합점수 {total:.0f}점. 펀더멘털 {fund_s:.0f}/"
                f"밸류 {val_s:.0f}/섹터 {sector_s:.0f}. 적정성 '{judgment}', 권고 '{action}'."
            ),
            key_risks=risks or ["오프라인 규칙기반 산출 — 정성적 리스크 평가 제한적"],
            catalysts=[],
            opinions=[macro_op, *opinions],
        )

    # --------------------------------------------------------------- 순위
    def rank(self, verdicts: list[StockVerdict]) -> tuple[list[RankingEntry], str]:
        ordered = sorted(verdicts, key=lambda v: v.total_score, reverse=True)
        entries = [
            RankingEntry(
                rank=i + 1,
                ticker=v.ticker,
                total_score=v.total_score,
                action=v.action,
                one_liner=f"{v.valuation_judgment}/{v.action}, 종합 {v.total_score:.0f}점",
            )
            for i, v in enumerate(ordered)
        ]
        if len(verdicts) == 1:
            summary = "단일 종목이므로 비교 순위는 생략합니다."
        else:
            top = entries[0]
            summary = (
                f"규칙기반 종합점수 기준 1위는 {top.ticker.display()} "
                f"({top.total_score:.0f}점). 점수가 높을수록 매수 매력도가 큼."
            )
        return entries, summary

    # --------------------------------------------------------- 포트폴리오
    def review_portfolio(self, review: PortfolioReview) -> PortfolioReview:
        risk = self.cfg.risk or {}
        stop_pct = float(risk.get("default_stop_loss_pct", 10))
        max_pos = float(risk.get("max_position_pct", 20))
        max_dd = float(risk.get("portfolio_max_drawdown_pct", 20))

        alerts: list[str] = []
        rebal: list[str] = []

        for p in review.positions:
            p.stop_loss = round(p.avg_price * (1 - stop_pct / 100.0), 2)
            # 조치 판단(우선순위: 손절 > 비중축소 > 익절 > 보유)
            if p.pnl_pct <= -stop_pct:
                p.action = "손절"
                p.flags.append(f"손절선 이탈({p.pnl_pct:+.1f}%)")
            elif p.weight_pct > max_pos * 1.5:
                p.action = "비중축소"
                p.flags.append(f"과대 집중({p.weight_pct:.0f}%)")
            elif p.pnl_pct >= 25:
                p.action = "일부익절"
                p.flags.append(f"이익 실현 구간(+{p.pnl_pct:.0f}%)")
            elif p.weight_pct > max_pos:
                p.action = "보유"
                p.flags.append(f"비중 주의({p.weight_pct:.0f}%)")
            else:
                p.action = "보유"
            p.comment = (
                f"수익률 {p.pnl_pct:+.1f}%, 비중 {p.weight_pct:.1f}% → '{p.action}' "
                f"(손절가 {p.stop_loss:,.0f})"
            )
            if p.weight_pct > max_pos:
                rebal.append(
                    f"{p.ticker.display()} 비중 {p.weight_pct:.0f}% → {max_pos:.0f}% 이하로 축소 검토"
                )

        # 포트폴리오 레벨 경고
        if review.positions:
            top = max(review.positions, key=lambda x: x.weight_pct)
            if top.weight_pct > max_pos:
                alerts.append(
                    f"최대 비중 종목 {top.ticker.display()} {top.weight_pct:.0f}% — 집중 위험"
                )
        for sec, w in review.sector_weights.items():
            if w > 40:
                alerts.append(f"섹터 '{sec}' 비중 {w:.0f}% — 섹터 집중 위험")
        if review.total_pnl_pct <= -max_dd:
            alerts.append(
                f"포트폴리오 평가손익 {review.total_pnl_pct:+.1f}% — 최대낙폭 한도({max_dd:.0f}%) 근접/초과"
            )
        losers = [p for p in review.positions if p.pnl_pct <= -stop_pct]

        review.risk_alerts = alerts or ["뚜렷한 집중/손실 경고 없음(규칙기반)"]
        review.rebalancing = rebal or ["현재 비중 정책 위반 없음"]
        review.summary = (
            f"규칙기반 점검: 총 {len(review.positions)}종목, "
            f"평가손익 {review.total_pnl_pct:+.1f}%. 손절 검토 {len(losers)}종목, "
            f"비중 초과 {len(rebal)}건. (정성 분석은 ANTHROPIC_API_KEY 설정 시 강화됨)"
        )
        return review
