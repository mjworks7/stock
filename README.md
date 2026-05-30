# 📊 StockAdvisor — 멀티 에이전트 주식 종목 분석

국내(KRX)·해외(US) 주식을 **매수/매도 전에 분석**하여 투자 방향을 제시하는 프로그램입니다.

- **주가 적정성 판단** — 저평가 / 적정 / 고평가
- **현재 시점 대응 방향** — 적극매수 / 분할매수 / 관망 / 비중축소 / 매도
- **투자 기간별 목표 금액** — 단기(1–3개월) / 중기(6–12개월) / 장기(1–3년) 목표가 밴드
- **손절가·권고 비중** 제시
- **여러 종목 입력 시 평가 + 추천 순위** 산출

## 🤝 전문가 에이전트가 직접 분석합니다

`.claude/agents/` 에 정의된 전문가 페르소나가 **런타임 시스템 프롬프트로 그대로 사용**되어,
프로그램 실행 시 실제로 토론·분석합니다.

| 에이전트 | 역할 | 담당 |
|---|---|---|
| `macro-regime-analyst` | 거시·시장국면 분석가 | 지금 주식 비중 늘릴 환경인가 |
| `industry-sector-analyst` | 산업·섹터 분석가 | 섹터 성장성·사이클 |
| `fundamental-analyst` | 펀더멘털 분석가 | 매출·이익·재무건전성 |
| `valuation-quant-analyst` | 밸류에이션·퀀트 분석가 | 주가가 싼가 비싼가 |
| `portfolio-risk-manager` | 포트폴리오·리스크 매니저 | 종합 판단·목표가·손절·순위 |

각 종목마다 `거시 → 섹터 → 펀더멘털 → 밸류에이션 → 리스크 종합` 순으로 분석하고,
여러 종목이면 리스크 매니저가 비교해 추천 순위를 매깁니다.

## ⚙️ 설치

```powershell
pip install -r requirements.txt
# 또는 패키지로 설치
pip install -e .
```

전문가 에이전트 실시간 분석(Claude API)을 쓰려면 키를 설정합니다:

```powershell
copy .env.example .env
# .env 를 열어 ANTHROPIC_API_KEY=sk-ant-... 입력
```

> 키가 없어도 동작합니다. 그 경우 **규칙기반(휴리스틱) 엔진**으로 정량 지표만으로 분석합니다.

## 🚀 사용법

```powershell
# 단일/복수 종목 (해외+국내 혼합 가능)
python run.py AAPL MSFT 005930 000660

# 설치했다면
python -m stockadvisor AAPL 005930
stockadvisor TSLA NVDA

# 네트워크/키 없이 스모크 테스트 (모의 데이터)
python run.py AAPL 005930 --offline

# JSON 결과도 저장
python run.py AAPL --json
```

- 종목 코드 규칙: **6자리 숫자 → 국내(KRX)**, 알파벳 → **미국**. (`005930` = 삼성전자, `AAPL` = 애플)
- 국내 종목은 `.KS`(코스피)/`.KQ`(코스닥)를 자동 판별합니다.

### 옵션

| 옵션 | 설명 |
|---|---|
| `--offline` | 모의 데이터 + 규칙기반 엔진 (네트워크/키 불필요) |
| `--json` | 리포트와 함께 JSON 결과 저장 |
| `--no-save` | 파일 저장 생략(콘솔만) |
| `--quiet` | 진행 로그 숨김 |
| `--config PATH` | config.yaml 경로 지정 |

## 📂 출력

- 콘솔에 마크다운 리포트 출력
- `reports/report_<시각>_<종목>.md` 로 저장 (`--json` 시 `.json` 도)

## 🏗️ 구조 (클린 아키텍처)

```
src/stockadvisor/
  domain/        # 순수 데이터 모델 (외부 의존 없음)
  data/          # 시세/재무 공급자 — MarketDataProvider 인터페이스로 교체 가능
                 #   free_provider(yfinance/FDR), mock_provider(오프라인)
  agents/        # 전문가 런타임 — 페르소나 로더 + LLM 엔진 / 규칙기반 엔진
  application/   # 오케스트레이션(service) + 리포트 생성(report)
  cli.py         # 명령행 진입점
```

데이터 계층이 인터페이스로 추상화되어 있어, 나중에 **유료 API(한국투자증권 OpenAPI,
Alpha Vantage 등)** 로 교체하려면 `MarketDataProvider` 를 구현한 클래스만 추가하면 됩니다.

## ⚙️ 설정 (`config.yaml`)

모델, 종합 점수 가중치, 손절/비중 정책, 투자 기간 정의 등을 조정할 수 있습니다.

## ⚠️ 유의

본 프로그램은 **참고용 분석 도구**이며 투자 권유가 아닙니다.
모든 투자 판단과 책임은 투자자 본인에게 있습니다. 자동 매매/주문 기능은 포함하지 않습니다.
