"""설정 로딩. config.yaml + 환경변수(.env)를 합쳐 단일 Config 객체로 제공."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # PyYAML 미설치 시에도 기본값으로 동작
    yaml = None  # type: ignore

# 프로젝트 루트 = 이 파일 기준 src/stockadvisor/ 에서 두 단계 위
PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = PROJECT_ROOT / ".claude" / "agents"

# config.yaml 이 없거나 PyYAML 이 없을 때 쓰는 내장 기본값
_DEFAULTS: dict[str, Any] = {
    "weights": {
        "macro": 0.15,
        "sector": 0.20,
        "fundamental": 0.30,
        "valuation": 0.25,
        "technical": 0.10,
    },
    "risk": {
        "max_position_pct": 20,
        "default_stop_loss_pct": 10,
        "portfolio_max_drawdown_pct": 20,
    },
    "horizons": {
        "short_term": "1-3개월",
        "mid_term": "6-12개월",
        "long_term": "1-3년",
    },
}


def _load_dotenv(root: Path) -> None:
    """python-dotenv가 있으면 .env 로드, 없으면 조용히 무시."""
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env")
    except Exception:  # pragma: no cover - 선택적 의존성
        pass


@dataclass
class Config:
    model: str = "claude-opus-4-8"
    max_tokens: int = 4000
    temperature: float = 0.3
    price_lookback_days: int = 400
    weights: dict[str, float] = field(default_factory=dict)
    risk: dict[str, Any] = field(default_factory=dict)
    horizons: dict[str, str] = field(default_factory=dict)
    report_dir: str = "reports"

    # 런타임 파생
    api_key: str | None = None
    # 한국투자증권(KIS) OpenAPI (국내 종목 정밀 데이터, 선택)
    kis_app_key: str | None = None
    kis_app_secret: str | None = None
    kis_paper: bool = False
    project_root: Path = PROJECT_ROOT
    agents_dir: Path = AGENTS_DIR

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    @property
    def has_kis(self) -> bool:
        return bool(self.kis_app_key and self.kis_app_secret)

    @property
    def report_path(self) -> Path:
        p = self.project_root / self.report_dir
        p.mkdir(parents=True, exist_ok=True)
        return p


def load_config(config_path: Path | None = None) -> Config:
    root = PROJECT_ROOT
    _load_dotenv(root)

    path = config_path or (root / "config.yaml")
    data: dict[str, Any] = {}
    if path.exists() and yaml is not None:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    cfg = Config(
        model=os.environ.get("STOCKADVISOR_MODEL", data.get("model", "claude-opus-4-8")),
        max_tokens=int(data.get("max_tokens", 4000)),
        temperature=float(data.get("temperature", 0.3)),
        price_lookback_days=int(data.get("price_lookback_days", 400)),
        weights=data.get("weights") or _DEFAULTS["weights"],
        risk=data.get("risk") or _DEFAULTS["risk"],
        horizons=data.get("horizons") or _DEFAULTS["horizons"],
        report_dir=data.get("report_dir", "reports"),
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        kis_app_key=os.environ.get("KIS_APP_KEY"),
        kis_app_secret=os.environ.get("KIS_APP_SECRET"),
        kis_paper=os.environ.get("KIS_PAPER", "").strip() in ("1", "true", "True"),
    )
    return cfg
