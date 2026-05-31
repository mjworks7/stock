# 📊 StockAdvisor — 멀티 에이전트 주식 종목 분석

국내(KRX)·해외(US) 주식을 **매수/매도 전에 분석**하여 투자 방향을 제시하는 프로그램입니다.

- **주가 적정성 판단** — 저평가 / 적정 / 고평가
- **현재 시점 대응 방향** — 적극매수 / 분할매수 / 관망 / 비중축소 / 매도
- **투자 기간별 목표 금액** — 단기(1–3개월) / 중기(6–12개월) / 장기(1–3년) 목표가 밴드
- **손절가·권고 비중** 제시
- **여러 종목 입력 시 평가 + 추천 순위** 산출
- **보유 종목 모니터링** — 평가손익·비중·집중도 점검 + 종목별 조치/리밸런싱 제안

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

### (선택) 국내 종목 정밀 데이터 — 한국투자증권(KIS) OpenAPI

국내 종목의 밸류에이션/재무 정확도를 높이려면 KIS 키를 설정합니다.
[apiportal.koreainvestment.com](https://apiportal.koreainvestment.com) 에서 앱 등록 후 발급:

```dotenv
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_PAPER=0          # 1 이면 모의투자 도메인
```

설정하면 **국내(6자리) 종목은 KIS, 해외 종목은 무료 공급자**로 자동 라우팅됩니다.
KIS 호출이 실패하면 자동으로 무료 공급자로 폴백합니다. (미설정 시 전 종목 무료 공급자)

## 🖥️ 웹 대시보드 (Streamlit)

브라우저에서 분석·모니터링을 한 화면에서:

```powershell
pip install -r requirements.txt
streamlit run dashboard.py
```

- **종목 분석 탭** — 종목 입력 → 추천 순위표 + 종목별 적정성·기간별 목표가·전문가 의견
- **보유 모니터링 탭** — `portfolio.yaml` 보유내역 자동 표시·저장, 표에서 종목 추가/편집(종목별 통화 선택), 종목별 **최근 분석 요약**(적정성·대응·목표가) 표시, 실행 시 평가손익·비중 차트·집중도 경고·리밸런싱
- 사이드바에서 **오프라인 모드** 토글, 엔진/데이터 출처 상태 확인, 리포트 다운로드

## 🚀 사용법 (CLI)

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

### 💼 보유 종목 모니터링

보유 중인 포트폴리오의 **평가손익·비중·집중도**를 점검하고, 종목별 조치
(추가매수/보유/일부익절/비중축소/손절)·손절가·리밸런싱 제안을 제시합니다.

```powershell
# 1) 예시를 복사해 본인 보유내역으로 수정 (portfolio.yaml 은 git 추적 제외)
copy portfolio.example.yaml portfolio.yaml

# 2) 모니터링 실행
python run.py monitor --file portfolio.yaml
python run.py monitor --file portfolio.yaml --offline   # 모의 데이터
```

포트폴리오 파일 형식(`portfolio.example.yaml` 참고):

```yaml
base_currency: KRW      # 비중/총액 환산 기준통화 (KRW 또는 USD)
cash: 1000000           # 보유 현금(선택)
holdings:
  - ticker: "005930"    # 국내는 6자리 코드(따옴표 권장)
    shares: 50
    avg_price: 70000    # 평균 매수단가(종목 통화)
  - ticker: AAPL
    shares: 20
    avg_price: 180
```

> KRW·USD 혼합 보유도 실시간 환율(USD/KRW)로 환산해 비중을 계산합니다.

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
                 #   free_provider(yfinance/FDR), kis_provider(한국투자증권),
                 #   composite_provider(시장별 라우팅), mock_provider(오프라인)
  agents/        # 전문가 런타임 — 페르소나 로더 + LLM 엔진 / 규칙기반 엔진
  application/   # 오케스트레이션(service) + 모니터링(monitor) + 리포트(report)
  cli.py         # 명령행 진입점 (analyze / monitor 서브커맨드)
dashboard.py     # Streamlit 웹 대시보드 (서비스 계층 재사용)
```

데이터 계층이 인터페이스로 추상화되어 있어, 다른 **유료 API(Alpha Vantage, Polygon 등)**
로 확장하려면 `MarketDataProvider` 를 구현한 클래스를 추가하고 `data/factory.py` 에 끼우면 됩니다.
국내 종목용 **한국투자증권(KIS) 공급자**는 이미 포함되어 있습니다(`data/kis_provider.py`).

## ⚙️ 설정 (`config.yaml`)

모델, 종합 점수 가중치, 손절/비중 정책, 투자 기간 정의 등을 조정할 수 있습니다.

## ⚠️ 유의

본 프로그램은 **참고용 분석 도구**이며 투자 권유가 아닙니다.
모든 투자 판단과 책임은 투자자 본인에게 있습니다. 자동 매매/주문 기능은 포함하지 않습니다.
