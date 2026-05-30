"""페르소나 로더 — .claude/agents/<name>.md 의 본문을 시스템 프롬프트로 사용.

이렇게 하면 사용자가 /agents 로 만든 전문가 정의가 그대로 런타임
분석가의 '두뇌'가 된다. 프롬프트를 코드에 중복 정의하지 않는다.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# 에이전트 이름 -> (한국어 역할명, 분석 관점 키)
AGENT_ROLES: dict[str, tuple[str, str]] = {
    "macro-regime-analyst": ("거시·시장국면 분석가", "macro"),
    "industry-sector-analyst": ("산업·섹터 분석가", "sector"),
    "fundamental-analyst": ("펀더멘털 분석가", "fundamental"),
    "valuation-quant-analyst": ("밸류에이션·퀀트 분석가", "valuation"),
    "portfolio-risk-manager": ("포트폴리오·리스크 매니저", "risk"),
    "project-orchestration-manager": ("프로젝트 총괄 매니저", "orchestration"),
}


def _strip_frontmatter(text: str) -> str:
    """YAML frontmatter(--- ... ---) 제거 후 본문만 반환."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return text.strip()


@lru_cache(maxsize=None)
def load_persona(agents_dir_str: str, agent_name: str) -> str:
    """에이전트 페르소나 본문(시스템 프롬프트) 로드. 없으면 합리적 폴백."""
    path = Path(agents_dir_str) / f"{agent_name}.md"
    if path.exists():
        return _strip_frontmatter(path.read_text(encoding="utf-8"))
    role = AGENT_ROLES.get(agent_name, (agent_name, ""))[0]
    return (
        f"You are an elite {role}. Analyze the provided stock data rigorously, "
        f"evidence-based, and decision-oriented. Respond in Korean."
    )
