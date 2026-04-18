---
name: daily_stock_analysis-dr
description: Use when working with daily_stock_analysis codebase — provides comprehensive module knowledge, design logic, and modification guides (generated from main branch, commit 37ab6f4)
---

# daily_stock_analysis -- Deep Code Skills Index

**Repo**: D:/claude/daily_stock_analysis
**Version**: commit 37ab6f4 (main branch)
**Generated**: 2026-04-15

This index covers all four modules of the daily_stock_analysis project. Each module has its own detailed skill document linked below.

---

## 1. Module Inventory

| Module | Purpose | Detailed Skill Doc |
|---|---|---|
| **src** | Multi-agent stock analysis system: pipeline orchestration, 6 specialized agents (Technical, Intel, Risk, Decision, Portfolio, Skill), LLM adapter (LiteLLM), tool registry, skill system, portfolio management, backtesting, notifications (11+ channels), web API, scheduling | [src SKILL.md](../daily_stock_analysis-dr-src/SKILL.md) |
| **data_provider** | Unified multi-source data fetching layer: 7 fetchers (Efinance, AkShare, Tushare, Pytdx, Baostock, Yfinance, Longbridge) with Strategy Pattern, automatic failover, circuit breaking, rate limiting, anti-ban. Covers A-shares, HK stocks, US stocks, US indices | [data_provider SKILL.md](../daily_stock_analysis-dr-data_provider/SKILL.md) |
| **strategies** | Natural-language trading strategy definitions in YAML: 11 built-in strategies across 4 categories (trend, pattern, reversal, framework). Loaded by SkillManager at startup, selected by SkillRouter via regime detection, injected into LLM system prompt | [strategies SKILL.md](../daily_stock_analysis-dr-strategies/SKILL.md) |
| **scripts** | Operational utilities: stock data pipeline (Tushare/AkShare CSV fetch + frontend index generation), analysis screening & review loop (short-term opportunity screening, recommendation save/review), build & CI tooling (macOS Bash + Windows PowerShell pairs) | [scripts SKILL.md](../daily_stock_analysis-dr-scripts/SKILL.md) |

### Quick Stats

- **Total Python files**: 200+ across all modules
- **Data sources**: 7 providers with automatic failover
- **Trading strategies**: 11 YAML-defined strategies, extensible without code changes
- **Notification channels**: 11+ (Email, Telegram, WeChat, Feishu, Discord, Slack, Pushover, PushPlus, ServerChan3, AstrBot, Custom Webhook)
- **Agent modes**: 4 (quick, standard, full, specialist)
- **Markets supported**: A-shares (Shanghai, Shenzhen, Beijing), HK, US

---

## 2. Inter-module Dependency Graph

```
                        +------------------+
                        |    strategies/   |
                        |  (YAML configs)  |
                        +--------+---------+
                                 | loaded by
                                 v
+-------------------+   +------------------+   +------------------+
|     scripts/      |   |       src/       |   |  data_provider/  |
| (operational util)|   | (analysis engine)|   |  (data fetching) |
+--------+----------+   +--------+---------+   +--------+---------+
         |                       |                      |
         | uses                  | calls via            | provides
         v                       v                      v
  screen_short_term_  -->  analyzer_service   -->  DataFetcherManager
  opportunity.py           .analyze_stock()         .get_daily_data()
                           .get_realtime_quote()    .get_realtime_quote()
  get_hot_sector_          .get_fundamental_        .get_chip_distribution()
  stocks.py                context()                .get_market_stats()
                           .get_sector_rankings()   .get_sector_rankings()
  review_recommenda-
  tions.py                                       uses
  save_recommendation.py
  generate_index_from_csv.py
  fetch_tushare_stock_list.py
```

### Dependency Directions

| From | To | Mechanism |
|---|---|---|
| `src/` | `data_provider/` | `DataFetcherManager` singleton used by agent data tools (`src/agent/tools/data_tools.py`). Lazy-initialized to avoid Tushare re-init overhead. |
| `src/` | `strategies/` | `SkillManager.load_builtin_skills()` scans `strategies/` at startup. `SkillRouter` selects skills by regime. Skill instructions injected into agent system prompts. |
| `scripts/` | `src/` | `screen_short_term_opportunity.py` imports `analyzer_service.analyze_stock()`. `review_recommendations.py` uses analysis results from the pipeline. |
| `scripts/` | `data_provider/` (indirect) | Via `src/` layer; some scripts (e.g., `review_recommendations.py`) call AkShare/EastMoney directly as fallback. |
| `strategies/` | `data_provider/` (declarative) | Strategy YAML files declare `required_tools` (e.g., `get_daily_history`, `get_realtime_quote`) which map to data_provider-backed agent tools. |
| `scripts/` | `strategies/` (none) | Scripts do not directly load strategies; strategy injection happens in the `src/` agent pipeline. |

### Data Flow Summary

```
data_provider/ (raw market data)
       |
       v
   src/ (analysis pipeline: agents + tools + skills)
       |
       v
   AnalysisResult (structured output)
       |
       +---> Notification (multi-channel dispatch)
       +---> Database (AnalysisHistory, PortfolioSnapshot)
       +---> Web API (REST + SSE)
       |
       v
   scripts/ (post-processing: review, screen, save recommendations)
```

---

## 3. Cross-Module Scenarios

### Scenario 1: Running a Single Stock Analysis

**Trigger**: User requests analysis of a specific stock (via web API, bot command, or CLI).

**Modules involved (in order)**:

1. **src/** -- Entry point (`api/v1/endpoints/agent.py` or `bot/commands/analyze.py`)
   - `resolve_name_to_code()` resolves stock name/image/import to canonical code
   - `Task Queue` enqueues or `Pipeline` runs synchronously
   - `StockAnalysisPipeline.run()` executes the 8-step pipeline

2. **src/** (Pipeline Step 1-3) -- Data preparation
   - `fetch_and_save_stock_data()` calls `DataFetcherManager.get_daily_data()`
   - Realtime quote augmentation via `DataFetcherManager.get_realtime_quote()`
   - Fundamental context aggregation (boards, sector rankings)

3. **data_provider/** -- Actual data fetching
   - `DataFetcherManager` iterates fetchers by priority (Tushare > Efinance > AkShare > Pytdx > Baostock > Yfinance > Longbridge)
   - Circuit breakers and rate limiting applied per source
   - Returns normalized DataFrame with STANDARD_COLUMNS + computed MA5/MA10/MA20

4. **src/** (Pipeline Step 5) -- Agent analysis
   - `AgentOrchestrator` builds agent chain based on mode (quick/standard/full/specialist)
   - Each agent runs `run_agent_loop()` (ReAct cycle) with tools from `ToolRegistry`
   - Tools call `DataFetcherManager` for data, `analyze_trend`/`analyze_pattern` for technical analysis

5. **strategies/** -- Skill injection (specialist mode)
   - `SkillManager.load_builtin_skills()` loads all `strategies/*.yaml`
   - `SkillRouter.select_skills()` picks strategies by regime (or user request)
   - `SkillAgent` evaluates each active strategy, outputs `score_adjustment`
   - `Aggregator` computes weighted consensus

6. **src/** (Pipeline Step 6-8) -- Output
   - `AnalysisResult` assembled with dashboard JSON
   - Persisted to `AnalysisHistory` table
   - `NotificationService` dispatches to configured channels

**Key files**: `src/core/pipeline.py`, `src/agent/orchestrator.py`, `src/agent/runner.py`, `data_provider/base.py`, `src/agent/skills/base.py`, `src/agent/skills/router.py`

---

### Scenario 2: Running Market Review

**Trigger**: Scheduled daily job (APScheduler) or manual API call for CN/US market recap.

**Modules involved (in order)**:

1. **src/** -- Market review entry (`src/core/market_review.py`)
   - `run_market_review()` determines active markets via `TradingCalendar.compute_effective_region()`
   - Fetches main indices via `DataFetcherManager.get_main_indices(region="cn"|"us")`
   - Fetches market breadth stats via `DataFetcherManager.get_market_stats()`

2. **data_provider/** -- Market-wide data
   - `get_main_indices()`: Returns 6 CN indices or 4 US indices (SPX, DJI, IXIC, VIX)
   - `get_market_stats()`: Up/down counts, limit-up/down, total turnover
   - `get_sector_rankings()`: Top/bottom performing industry sectors

3. **src/** -- Strategy blueprint selection
   - `MarketStrategyBlueprint` selects region-specific strategy (CN: A-share focused, US: index-focused)
   - `MarketStrategyBlueprint.to_markdown_block()` renders the strategy framework

4. **strategies/** -- Market-context strategies
   - If `sector_hot` regime detected, `dragon_head` and `emotion_cycle` strategies may be included
   - Market review uses strategy blueprints from `src/core/market_strategy.py`, not individual strategy YAML files directly

5. **src/** -- Report generation and dispatch
   - Markdown report assembled with index performance, sector rotation, strategy outlook
   - `NotificationService.send(content, email_send_to_all=True)` broadcasts to all email recipients
   - Report saved to file

**Key files**: `src/core/market_review.py`, `src/core/market_strategy.py`, `src/core/trading_calendar.py`, `data_provider/base.py`, `src/notification.py`

---

### Scenario 3: Screening for Short-Term Opportunities

**Trigger**: User invokes the `short-term-picker` skill or runs the screening script.

**Modules involved (in order)**:

1. **scripts/** -- Candidate generation
   - `get_hot_sector_stocks.py` fetches sector constituent stocks via AkShare `stock_board_concept_cons_em()`
   - Falls back to `CURATED_STOCKS` dictionary if network/API fails
   - Outputs JSON array to stdout

2. **scripts/** -- Scoring
   - `screen_short_term_opportunity.py` reads candidates (from file or CLI args)
   - For each stock: imports `src/services/analysis_service.py` -> `analyze_stock()`
   - **src/** runs the full analysis pipeline (data fetch -> agent analysis -> result) for each candidate
   - `score_stock()` function computes composite score:
     - Trend score (40% base): sentiment_score + trend_prediction bonus/penalty
     - Buy-point score (35% base): operation_advice + decision_type
     - Short-term probability (25% base): confidence_level + keyword matching
   - Outputs top-N ranked results as JSON

3. **scripts/** -- Persistence (optional)
   - `save_recommendation.py` appends selected recommendation to `data/recommendations_history.json`
   - Auto-increments ID, records full metadata (price, score, support/resistance, stop-loss, take-profit)

4. **scripts/** -- Retrospective review (later)
   - `review_recommendations.py` reads past recommendations, fetches current prices (AkShare -> EastMoney fallback)
   - Computes actual return, success/failure/neutral classification
   - Writes `data/review_report.json` with accuracy rate and lessons learned

**Key files**: `scripts/get_hot_sector_stocks.py`, `scripts/screen_short_term_opportunity.py`, `scripts/save_recommendation.py`, `scripts/review_recommendations.py`, `src/services/analysis_service.py`

---

### Scenario 4: Adding a New Trading Strategy

**Trigger**: Developer wants to add a new trading pattern (e.g., "double bottom bounce").

**Modules involved (in order)**:

1. **strategies/** -- Create strategy YAML
   - Create `strategies/double_bottom_bounce.yaml` with required fields:
     - `name`, `display_name`, `description`, `instructions` (natural-language rules)
   - Optional metadata:
     - `category` (trend/pattern/reversal/framework) -- determines prompt rendering order
     - `default_priority` -- numeric ordering (lower = shown first)
     - `market_regimes` -- regime tags for router auto-selection (trending_up, trending_down, sideways, volatile, sector_hot)
     - `required_tools` -- tool names the LLM should use (e.g., `get_daily_history`, `analyze_trend`)
     - `core_rules` -- referenced principle numbers (1-7 from `strategies/README.md`)
     - `default_active` / `default_router` -- activation flags
   - No Python code changes required

2. **src/** -- Automatic loading (no changes needed)
   - `SkillManager.load_builtin_skills()` auto-scans `strategies/` for `*.yaml` on startup
   - Strategy becomes available for:
     - Explicit user request by `name`
     - Router selection if `market_regimes` match detected regime
     - Default activation if `default_active: true`
     - Router fallback if `default_router: true`

3. **strategies/** -- Testing
   - Instructions are injected verbatim into the LLM system prompt
   - The LLM interprets the rules and decides which tools to call
   - Test by running analysis with the strategy explicitly requested

**Key files**: `strategies/double_bottom_bounce.yaml` (new), `src/agent/skills/base.py` (loader, no changes), `src/agent/skills/router.py` (router, no changes), `strategies/README.md` (optional: document new strategy)

---

### Scenario 5: Adding a New Data Source

**Trigger**: Developer wants to integrate a new market data provider (e.g., "Wind API").

**Modules involved (in order)**:

1. **data_provider/** -- Create new fetcher
   - Create `data_provider/wind_fetcher.py` extending `BaseFetcher` from `data_provider/base.py`
   - Implement abstract methods:
     - `_fetch_raw_data(stock_code, start_date, end_date) -> pd.DataFrame`
     - `_normalize_data(df, stock_code) -> pd.DataFrame` (map columns to `STANDARD_COLUMNS`)
   - Optionally override: `get_realtime_quote()`, `get_chip_distribution()`, `get_stock_name()`, `get_main_indices()`, `get_market_stats()`, `get_sector_rankings()`
   - Set `name` and `priority` class attributes (or make configurable via env var)

2. **data_provider/** -- Register in manager
   - Update `DataFetcherManager._init_default_fetchers()` (`base.py`): import and instantiate the new fetcher, add to `self._fetchers`
   - Update `data_provider/__init__.py` exports
   - If providing realtime quotes: add to `realtime_source_priority` config handling and `bulk_sources` in `prefetch_realtime_quotes()`

3. **src/** -- No changes needed (if standard methods implemented)
   - Agent tools (`data_tools.py`) call `DataFetcherManager` methods, which already handle failover across all registered fetchers
   - The new fetcher participates automatically in the priority-based failover chain

4. **strategies/** -- No changes needed
   - Strategies declare `required_tools` by name (e.g., `get_daily_history`), not by source
   - The data layer abstracts source selection from strategy definitions

5. **data_provider/** -- Optional: anti-ban measures
   - If the new source is crawler-based, add: random jitter sleep, User-Agent rotation, exponential backoff retry (via tenacity `@retry`), circuit breaker integration

**Key files**: `data_provider/wind_fetcher.py` (new), `data_provider/base.py` (register in `_init_default_fetchers`), `data_provider/__init__.py` (exports), `data_provider/realtime_types.py` (circuit breaker if needed)

---

### Scenario 6 (Bonus): Adding a New Notification Channel

**Trigger**: Developer wants to add a new notification destination (e.g., "Matrix/Element").

**Modules involved**:

1. **src/** -- Create sender class
   - Create `src/notification_sender/matrix_sender.py`
   - Implement `MatrixSender` with `send_to_matrix(content, ...)` method
   - Follow pattern: check `_is_configured()`, handle chunked sending for long content, return bool

2. **src/** -- Register in notification service
   - Update `src/notification_sender/__init__.py`: export `MatrixSender`
   - Update `src/notification.py`: import, add config check, add send path in `NotificationService.send()`

3. **src/** -- Add configuration fields
   - Update `src/config.py`: add `matrix_webhook_url`, `matrix_room_id`, `matrix_enabled`, etc.

**Key files**: `src/notification_sender/matrix_sender.py` (new), `src/notification.py`, `src/config.py`

---

## 4. Architecture at a Glance

```
+------------------------------------------------------------------+
|                        User Interfaces                           |
|  Web API (FastAPI) | Bot Commands | CLI | Scheduled Jobs (APScheduler) |
+------------------------+-----------------------------------------+
                         |
                         v
+--------------------------------------------------------------+
|                    src/  (Analysis Engine)                    |
|  +----------------------------------------------------------+ |
|  |  Pipeline  |  Agents  |  Tools  |  Skills  |  Portfolio  | |
|  |  Orchestrator  |  ReAct  |  Registry  |  Router  |  Backtest  | |
|  +----------------------------------------------------------+ |
|  |  Notifications (11+ channels)  |  Config  |  Task Queue  | |
|  +----------------------------------------------------------+ |
+----------------------------+---------------------------------+
                             | calls
                             v
+--------------------------------------------------------------+
|              data_provider/  (Data Fetching Layer)            |
|  DataFetcherManager -> [Efinance | AkShare | Tushare | ... ] |
|  Circuit Breakers | Rate Limiting | Anti-Ban | Failover       |
+--------------------------------------------------------------+
                             ^
                             | reads
+--------------------------------------------------------------+
|               strategies/  (Trading Strategy YAML)            |
|  bull_trend | ma_golden_cross | volume_breakout | chan_theory |
|  wave_theory | dragon_head | emotion_cycle | ...              |
+--------------------------------------------------------------+
                             |
                             v (post-processing)
+--------------------------------------------------------------+
|                 scripts/  (Operational Utilities)             |
|  Screening | Review | Index Generation | Build | CI           |
+--------------------------------------------------------------+
```

## 5. Configuration Entry Points

| Concern | Config Location | Key Fields |
|---|---|---|
| LLM providers | `.env` / `LLM_CHANNELS` | protocol, base_url, api_key, model |
| Data source priority | `src/config.py` | `realtime_source_priority`, `TUSHARE_TOKEN` |
| Agent mode | `src/config.py` | `agent_arch` (single/multi), `agent_mode` (quick/standard/full/specialist) |
| Skills | `src/config.py` | `agent_skills`, `agent_skill_routing`, `AGENT_SKILL_DIR` |
| Notifications | `src/config.py` | Per-channel enabled flags (e.g., `telegram_enabled`, `feishu_webhook`) |
| Portfolio | `src/config.py` | `portfolio_enabled`, `cost_method` (fifo/avg) |
| Concurrency | `src/config.py` | `max_workers` |
| Memory/Calibration | `.env` | `AGENT_MEMORY_ENABLED=true` |

## 6. File Reference Map

```
D:/claude/daily_stock_analysis/
├── src/
│   ├── core/           # Pipeline, orchestrator, backtest, market_review, trading_calendar
│   ├── agent/          # Agents, ReAct runner, LLM adapter, tools, skills, factory, memory
│   ├── services/       # Portfolio, analysis, task_queue, history, config, notification
│   ├── notification_sender/  # 11 channel implementations
│   ├── data/           # stock_mapping.py, stock_index_loader.py
│   ├── config.py       # Central Config dataclass (150+ fields)
│   ├── analyzer.py     # AnalysisResult dataclass, GeminiAnalyzer
│   ├── storage.py      # DatabaseManager + ORM models (SQLite)
│   └── notification.py # Multi-channel dispatcher
├── data_provider/
│   ├── base.py         # BaseFetcher, DataFetcherManager, STANDARD_COLUMNS
│   ├── efinance_fetcher.py   # Priority 0 (or configurable)
│   ├── akshare_fetcher.py    # Priority 1
│   ├── tushare_fetcher.py    # Priority -1 (when token configured)
│   ├── pytdx_fetcher.py      # Priority 2
│   ├── baostock_fetcher.py   # Priority 3
│   ├── yfinance_fetcher.py   # Priority 4
│   ├── longbridge_fetcher.py # Priority 5
│   └── realtime_types.py     # UnifiedRealtimeQuote, ChipDistribution, CircuitBreaker
├── strategies/
│   ├── bull_trend.yaml         # Default trend strategy (category: trend)
│   ├── ma_golden_cross.yaml    # MA crossover detection
│   ├── volume_breakout.yaml    # Volume-confirmed breakout
│   ├── shrink_pullback.yaml    # Shrink-volume pullback
│   ├── dragon_head.yaml        # Sector leader
│   ├── one_yang_three_yin.yaml # K-line pattern
│   ├── bottom_volume.yaml      # Bottom volume reversal
│   ├── box_oscillation.yaml    # Range-bound trading
│   ├── chan_theory.yaml        # Zen channel theory
│   ├── wave_theory.yaml        # Elliott Wave
│   ├── emotion_cycle.yaml      # Sentiment cycle
│   └── README.md               # Core principles + YAML templates
├── scripts/
│   ├── get_hot_sector_stocks.py         # Hot sector constituent stocks
│   ├── screen_short_term_opportunity.py # Short-term scoring
│   ├── save_recommendation.py           # Recommendation persistence
│   ├── review_recommendations.py        # Retrospective review
│   ├── fetch_tushare_stock_list.py      # Tushare stock list fetch
│   ├── generate_index_from_csv.py       # Frontend index generation
│   ├── generate_stock_index.py          # MVP index from STOCK_NAME_MAP
│   ├── check_ai_assets.py               # AI governance checker
│   ├── ci_gate.sh                       # CI gate script
│   └── build-*.sh / build-*.ps1         # Cross-platform build scripts
└── docs/deep-read/                      # This document and module skill docs
    ├── daily_stock_analysis-dr-src/SKILL.md
    ├── daily_stock_analysis-dr-data_provider/SKILL.md
    ├── daily_stock_analysis-dr-strategies/SKILL.md
    ├── daily_stock_analysis-dr-scripts/SKILL.md
    └── daily_stock_analysis-dr/SKILL.md  # <-- You are here
```
