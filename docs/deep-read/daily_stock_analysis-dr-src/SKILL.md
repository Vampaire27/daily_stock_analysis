---
name: daily_stock_analysis-dr-src
description: Comprehensive deep-read skill document for the `src` module of the daily_stock_analysis repository. Covers module purpose, core design logic, data structures, state flow, and common modification scenarios.
---

# SKILL: daily_stock_analysis `src` Module Deep-Read

## 1. Module Purpose & Capabilities

The `src/` module is a complete multi-agent stock analysis system for A-shares, US stocks, and HK stocks. It provides:

- **Multi-Agent Analysis Pipeline**: 6 specialized agents (Technical, Intel, Risk, Decision, Portfolio, Skill) coordinated by an `AgentOrchestrator` with four modes (quick/standard/full/specialist)
- **Real-time and Historical Data Fetching**: Multi-provider data layer (Tushare, AkShare, yfinance, Sina, Tencent) with failover and canonical code normalization
- **LLM-Powered Reasoning**: LiteLLM-based adapter supporting Gemini, Anthropic, OpenAI, DeepSeek, MiniMax with multi-key load balancing and fallback chains
- **Skill System**: YAML/Markdown-based trading skills with regime-based routing and weighted consensus
- **Portfolio Management**: Full account/trade/snapshot lifecycle with FIFO/avg cost, multi-currency FX conversion, and corporate actions
- **Backtesting Engine**: Pure-logic evaluation of predicted direction vs. actual price movement with stop-loss/take-profit simulation
- **Notifications**: 11+ channel senders (Email, Telegram, WeChat Work, Feishu, Discord, Slack, Pushover, PushPlus, ServerChan3, AstrBot, Custom Webhook)
- **Market Review**: Daily recap for CN/US markets with region-specific strategy blueprints
- **Web API**: REST endpoints for analysis, portfolio, history, configuration, and SSE task status
- **Scheduling**: APScheduler-based daily automation with calendar-aware trading day computation

---

## 2. Core Design Logic

### 2.1 Pipeline Orchestration (`src/core/pipeline.py`)

`StockAnalysisPipeline` is the top-level orchestrator. Key method: `run()` which uses `ThreadPoolExecutor(max_workers)` to process multiple stocks concurrently. Each stock flows through 8 steps:

1. **Data Fetch**: `fetch_and_save_stock_data()` with checkpoint/resume logic
2. **Realtime Augment**: Inject intraday quote for live MA calculation
3. **Fundamental Context**: Aggregate sector rankings, belong_boards, financial data
4. **Social Sentiment**: (US stocks only) via `SocialSentimentService`
5. **Analysis**: Agent mode (`_analyze_with_agent()`) or traditional (`StockTrendAnalyzer`)
6. **Result Assembly**: Build `AnalysisResult` with dashboard JSON
7. **Persistence**: Save to `AnalysisHistory` table
8. **Notification**: Dispatch via `NotificationService` with md2img fallback

Design decision: The pipeline uses `AnalysisResult` dataclass as the single output contract between all stages, enabling both agent and traditional paths to produce identical downstream results.

### 2.2 Multi-Agent Architecture (`src/agent/`)

**Agent Orchestration** (`src/agent/orchestrator.py`):
- `AgentOrchestrator._execute_pipeline()`: Sequential agent chain with timeout/budget management
- `_build_agent_chain()`: Instantiates agents based on mode
  - `quick`: Technical -> Decision
  - `standard`: Technical -> Intel -> Decision
  - `full`: Technical -> Intel -> Risk -> Decision
  - `specialist`: full + SkillAgent(s) injected before Decision
- `_apply_risk_override()`: RiskAgent can downgrade or veto buy signals
- `_resolve_final_output()`: Graceful degradation when stages fail
- Stock code extraction via regex: A-share (6-digit), HK (HK-prefix + 5-digit), US (2-5 uppercase letters excluding common English words)

**ReAct Loop** (`src/agent/runner.py`):
- `run_agent_loop()`: Single authoritative ReAct implementation, shared by AgentExecutor and all agents
- Tool execution: Single inline or parallel via `ThreadPoolExecutor` (up to 5 workers)
- Non-retriable tool caching via `_build_tool_cache_key()` (normalizes stock codes for cache sharing)
- Configurable per-batch timeout

**LLM Adapter** (`src/agent/llm_adapter.py`):
- `LLMToolAdapter.call_with_tools()`: Tool-calling with LiteLLM
- `LLMToolAdapter.call_text()`: Text-only completion
- `call_completion()`: Iterates `models_to_try` with rate-limit backoff
- Handles DeepSeek/Qwen thinking content, MiniMax content_blocks format
- Custom pricing registered for MiniMax-M2.7/M2.5

### 2.3 Tool System (`src/agent/tools/`)

- **Registry**: `ToolRegistry` with `@tool` decorator, `to_openai_tools()` for LiteLLM format
- **Data Tools** (`data_tools.py`): `get_realtime_quote`, `get_daily_history`, `get_chip_distribution`, `get_analysis_context`, `get_stock_info`, `get_portfolio_snapshot`, `get_capital_flow`
  - `DataFetcherManager` singleton with lazy initialization (avoids Tushare re-init overhead)
  - `_compact_fundamental_context()` and `_compact_portfolio_snapshot()` reduce token footprint
- **Analysis Tools** (`analysis_tools.py`): `analyze_trend`, `calculate_ma`, `get_volume_analysis`, `analyze_pattern`
  - Pattern recognition: Doji, Hammer, Shooting Star, Morning/Evening Star, Engulfing, Double Bottom, breakout, box oscillation
- **Search Tools** (`search_tools.py`): `search_stock_news`, `search_comprehensive_intel`

### 2.4 Skill System (`src/agent/skills/`)

- **Skill Loading** (`base.py`): YAML/Markdown-based trading skills with 20+ fields
- **Router** (`router.py`): Priority selection: user-requested > manual config > regime-detected > default fallback
  - `_detect_regime()`: Examines technical opinion for trending_up/trending_down/sideways/volatile/sector_hot
- **SkillAgent** (`skill_agent.py`): Wraps a single skill for evaluation, outputs score_adjustment (-20 to +20)
- **Aggregator** (`aggregator.py`): Weighted consensus (weight = confidence * perf_weight), signal scoring: strong_buy=5, buy=4, hold=3, sell=2, strong_sell=1
- **Defaults** (`defaults.py`): CORE_TRADING_SKILL_POLICY_ZH (7 rules), TECHNICAL_SKILL_RULES_EN

### 2.5 Portfolio System (`src/services/`)

**PortfolioService** (`portfolio_service.py`):
- Account CRUD, trade events, cash ledger, corporate actions
- Snapshot replay: `_replay_account()` processes events in deterministic order (cash -> corp -> trade)
- FIFO and average cost methods (`_consume_fifo_lots()`, `_consume_avg_position()`)
- Multi-currency FX conversion via `_convert_amount()` with yfinance fallback
- Oversell protection via `_validate_sell_quantity()`

**PortfolioImportService** (`portfolio_import_service.py`):
- Parser registry for broker CSV formats (Huatai, Citic, CMB)
- Extensible `CsvParserSpec` with column hint mapping
- Dedup via trade_uid + SHA256 dedup_hash

**PortfolioRiskService** (`portfolio_risk_service.py`):
- Concentration alerts (per-symbol and per-sector)
- Drawdown computation from daily snapshot series
- Stop-loss proximity detection

### 2.6 Backtest Engine (`src/core/backtest_engine.py`)

`BacktestEngine` is pure logic, DB-agnostic:
- `evaluate_single()`: Checks if predicted direction matched actual return over eval_window_days
- `_classify_outcome()`: win/loss/neutral based on neutral_band_pct
- `_evaluate_targets()`: Stop-loss/take-profit with first_hit detection; if both hit in same bar -> "ambiguous", assumes stop-loss first
- `compute_summary()`: Aggregates win_rate, direction_accuracy, stop_loss_trigger_rate, advice_breakdown

### 2.7 Configuration Management (`src/config.py`, `src/services/system_config_service.py`)

- 150+ field `Config` dataclass with singleton pattern
- Channel-based LLM routing via `LLM_CHANNELS` env var or LiteLLM YAML config
- `SystemConfigService` handles `.env` read/validate/update/import with version conflict detection
- LLM channel validation: protocol, base_url SSRF blocking, API key presence, model declaration matching

### 2.8 Notification Architecture (`src/notification.py`, `src/notification_sender/`)

**NotificationService** (`src/notification.py`):
- Central dispatcher that aggregates all channel senders
- `send()`: Sends to all configured channels with failure tolerance
- `email_send_to_all=True` parameter for market review broadcast
- Markdown-to-image fallback via `md2img` module

**Individual Senders** (11 channels):
- `EmailSender`: SMTP with auto-detection (QQ, 163, Gmail, Outlook, etc.), inline image support, stock_email_groups for per-stock routing
- `TelegramSender`: Bot API with Markdown conversion, chunked sending, exponential backoff retry, rate-limit handling
- `FeishuSender`: Webhook with HMAC signing, keyword prefix, lark_md interactive cards, chunked sending
- `WechatSender`: Enterprise WeChat webhook (markdown/text/image types)
- `DiscordSender`: Webhook or Bot API
- `SlackSender`: Bot API (preferred) or Incoming Webhook, Block Kit support, file upload API for images
- `PushoverSender`: Plain text with 1024-char limit, chunked
- `PushplusSender`: Markdown template, topic support
- `Serverchan3Sender`: WeChat push via ftqq.com
- `AstrbotSender`: Bot adapter with HMAC request signing
- `CustomWebhookSender`: Auto-detects DingTalk/Discord/Slack/Bark formats

### 2.9 Name-to-Code Resolution (`src/services/name_to_code_resolver.py`)

Resolution strategy (in order):
1. Code-like input passthrough (5-6 digits, 1-5 letters, prefixed codes)
2. Local `STOCK_NAME_MAP` reverse lookup (excludes ambiguous names)
3. Pinyin match (via pypinyin)
4. AkShare online fallback (A-shares, 30-min cache)
5. Fuzzy match (difflib, cutoff=0.8, single-char typo fallback at 0.7)
6. Non-CJK free text skip (avoids false positives on random Latin noise)

### 2.10 Import Parser (`src/services/import_parser.py`)

- Parses CSV/Excel/clipboard text into (code, name, confidence) items
- Auto-detects column headers from aliases (`code`, `股票代码`, `symbol`, etc.)
- Single-column fast path for plain lists
- Resolution via `resolve_name_to_code()` for name-only inputs
- Size limits: 2MB file, 100KB text

### 2.11 Vision Image Extractor (`src/services/image_stock_extractor.py`)

- Extracts stock codes from screenshots using Vision LLM
- Priority: Gemini -> Anthropic -> OpenAI (first available)
- Multi-key rotation with exponential backoff (3 attempts)
- Magic byte verification to reject forged MIME types
- JSON response parsing with `json_repair` fallback
- Single-char typo tolerance (e.g., "贵州茅苔" -> "贵州茅台")

### 2.12 Social Sentiment (`src/services/social_sentiment_service.py`)

- Fetches Reddit/X/Polymarket data from api.adanos.org
- Only activates for US stocks, requires `SOCIAL_SENTIMENT_API_KEY`
- TTL cache (10 minutes) for trending endpoints
- Inflight dedup via `threading.Event`

### 2.13 Task Queue (`src/services/task_queue.py`)

- `AnalysisTaskQueue`: Singleton with thread pool execution
- Duplicate stock prevention via canonical dedupe key
- SSE event broadcasting via `call_soon_threadsafe` to asyncio queues
- `sync_max_workers()`: Dynamic concurrency adjustment (applies only when idle)
- Task lifecycle: PENDING -> PROCESSING -> COMPLETED/FAILED

### 2.14 Trading Calendar (`src/core/trading_calendar.py`)

- `exchange-calendars` integration with fail-open design
- `get_market_for_stock()`: Infers market from code prefix
- `is_market_open()`: Checks session availability
- `compute_effective_region()`: Filters market review by open markets

### 2.15 Factory Pattern (`src/agent/factory.py`)

- `build_agent_executor(config, skills=None)`: Central entry point for constructing AgentExecutor or AgentOrchestrator
- Decision logic: checks `config.agent_arch` (defaults to `'single'`). If `'multi'`, calls `_build_orchestrator()` returning `AgentOrchestrator`; otherwise returns `AgentExecutor`
- **ToolRegistry caching**: Built once at module level in `_TOOL_REGISTRY`, reused across all requests (immutable after setup)
- **SkillManager prototype caching**: Prototype built on first call, stored in `_SKILL_MANAGER_PROTOTYPE`. Each request gets a `deepcopy` clone for thread safety (since `activate()` mutates internal state)
- **Cache invalidation**: SkillManager cache invalidates when `AGENT_SKILL_DIR` changes at runtime (tracked via `_SKILL_MANAGER_CUSTOM_DIR` sentinel)
- `resolve_skill_prompt_state()`: Resolves which skills to activate, returns `SkillPromptState` with activated skills, explicit_selection flag, and rendered prompt fragments
- Skill resolution priority: requested_skills > configured_skills > default_skills (via `_resolve_selected_skill_ids()`)
- `SkillPromptState` dataclass: `skill_manager`, `skills_to_activate`, `explicit_skill_selection`, `use_legacy_default_prompt`, `skill_instructions`, `default_skill_policy`, `technical_skill_policy`

### 2.16 AgentMemory (`src/agent/memory.py`)

- **Three capabilities**: analysis history retrieval, confidence calibration, skill performance tracking
- **Gated by**: `AGENT_MEMORY_ENABLED=true` (default False). When disabled, all methods return neutral/default values
- **Minimum calibration samples**: `_MIN_CALIBRATION_SAMPLES = 30`. Calibration only activates after this threshold
- **Confidence calibration algorithm**: `get_calibration()` computes `calibration_factor = min(1.5, max(0.5, historical_accuracy / avg_confidence))`. If agent is overconfident → factor < 1; if underconfident → factor > 1. Factor clamped to [0.5, 1.5]
- **`calibrate_confidence()`**: Applies calibration factor to raw confidence: `adjusted = raw_confidence * calibration_factor`, clamped to [0.0, 1.0]
- **Skill weight calculation**: `skill_weight = 0.5 + win_rate` for skills with sufficient samples, normalized so mean = 1.0
- **`get_stock_history(stock_code, limit=5)`**: Retrieves `AnalysisMemoryEntry` objects with signal, sentiment_score, price_at_analysis, outcome_5d, outcome_20d, was_correct
- **Rolling window**: `_ROLLING_WINDOW = 50` for recent accuracy calculation
- Uses `AnalysisHistory` + `BacktestResult` tables in the existing SQLite database

### 2.17 Risk Override (`src/agent/orchestrator.py`)

- `_apply_risk_override()`: Method in AgentOrchestrator that applies RiskAgent findings to downgrade Decision signals
- **Gated by**: `config.agent_risk_override` (default True)
- **Idempotent**: Skips if `risk_override_applied` already set in context
- **Veto mechanism**: When RiskAgent flags a high-severity risk (e.g., veto_buy=True), the orchestrator downgrades 'buy' signal to 'hold'
- **Signal downgrade levels**: `signal_adjustment='downgrade_one'` moves signal one step down in `['buy', 'hold', 'sell']`; `signal_adjustment='downgrade_two'` moves two steps
- **Dashboard marking**: When override applied, dashboard gets `[风控下调: X -> Y]` prefix to indicate risk-caused downgrade
- **`_downgrade_signal()`**: Helper method that maps current signal to downgraded signal

---

## 3. Core Data Structures

### 3.1 Agent Communication (`src/agent/protocols.py`)

```python
@dataclass
class AgentContext:
    """Shared state bag passed between agents."""
    stock_code: str
    mode: str              # quick/standard/full/specialist
    opinions: Dict[str, 'AgentOpinion']  # stage -> opinion
    data: Dict[str, Any]   # scratch pad
    memory_context: str    # history injection

@dataclass
class AgentOpinion:
    """Structured output per agent."""
    agent_name: str
    signal: str            # buy/sell/hold
    confidence: int        # 0-100
    reasoning: str
    key_levels: Dict[str, float]
    raw_output: str

@dataclass
class StageResult:
    """Pipeline stage outcome."""
    success: bool
    output: Optional[Dict]
    error: Optional[str]
    stats: Dict[str, Any]
```

`normalize_decision_signal()` maps: strong_buy -> buy, strong_sell -> sell.

### 3.2 Analysis Result (`src/analyzer.py`)

`AnalysisResult` dataclass (40+ fields):
- Core: `code`, `name`, `sentiment_score`, `operation_advice`, `trend_prediction`, `decision_type`
- Dashboard: `dashboard` (nested JSON with core_conclusion, data_perspective, intelligence, battle_plan)
- Analysis sections: `technical_analysis`, `fundamental_analysis`, `news_summary`, `risk_warning`
- Sniper points: `ideal_buy`, `secondary_buy`, `stop_loss`, `take_profit`
- Metadata: `report_language`, `model_used`, `current_price`, `change_pct`

### 3.3 Tool Registry (`src/agent/tools/registry.py`)

```python
@dataclass
class ToolParameter:
    name: str
    type: str  # string/number/integer/boolean/array/object
    description: str
    required: bool = True
    enum: Optional[List[str]] = None
    default: Any = None

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: List[ToolParameter]
    handler: Callable
    category: str  # data/analysis/search/market/backtest

class ToolRegistry:
    _tools: Dict[str, ToolDefinition]
    # Methods: register, unregister, get, list_tools, execute, to_openai_tools
```

### 3.4 Skill Data (`src/agent/skills/base.py`)

`Skill` dataclass with 20+ fields: `name`, `display_name`, `description`, `instructions`, `category`, `core_rules`, `required_tools`, `market_regimes`, `activation_conditions`, etc.

### 3.5 Portfolio Data (`src/services/portfolio_service.py`)

- `_AvgState`: quantity + total_cost for average cost tracking
- Snapshot structure: accounts[].positions[] with symbol, market, currency, quantity, avg_cost, last_price, market_value_base, unrealized_pnl_base
- Event types: cash, trade, corp (corporate action)
- Event ordering priority: {"cash": 0, "corp": 1, "trade": 2}

### 3.6 Backtest Protocols (`src/core/backtest_engine.py`)

```python
class DailyBarLike(Protocol):
    date: date
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]

class BacktestResultLike(Protocol):
    eval_status: str
    position_recommendation: Optional[str]
    outcome: Optional[str]
    direction_correct: Optional[bool]
    stock_return_pct: Optional[float]
    simulated_return_pct: Optional[float]
    hit_stop_loss: Optional[bool]
    hit_take_profit: Optional[bool]
    first_hit: Optional[str]
    first_hit_trading_days: Optional[int]
    operation_advice: Optional[str]

@dataclass(frozen=True)
class EvaluationConfig:
    eval_window_days: int
    neutral_band_pct: float = 2.0
    engine_version: str = "v1"
```

### 3.7 Market Strategy Blueprint (`src/core/market_strategy.py`)

```python
@dataclass(frozen=True)
class StrategyDimension:
    name: str
    objective: str
    checkpoints: List[str]

@dataclass(frozen=True)
class MarketStrategyBlueprint:
    region: str
    title: str
    positioning: str
    principles: List[str]
    dimensions: List[StrategyDimension]
    action_framework: List[str]
    # Methods: to_prompt_block(), to_markdown_block()
```

### 3.8 Task Queue Data (`src/services/task_queue.py`)

```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class TaskInfo:
    task_id: str
    stock_code: str
    stock_name: Optional[str]
    status: TaskStatus
    progress: int
    message: Optional[str]
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    report_type: str
    created_at: datetime
    # Methods: to_dict(), copy()
```

---

## 4. State Flow

### 4.1 Single Stock Analysis Flow

```
User Input (code/name/image/import)
  -> resolve_name_to_code() / extract_stock_codes_from_image() / parse_import_from_bytes()
  -> canonical_stock_code() normalization
  -> Task Queue (async) or Pipeline (sync)
    -> StockAnalysisPipeline.run() / analyze_stock()
      -> fetch_and_save_stock_data() [checkpoint: if fresh data exists, skip]
      -> Realtime quote augmentation (intraday)
      -> Fundamental context aggregation (boards, sector rankings, earnings)
      -> Social sentiment (US only)
      -> Agent or Traditional analysis path:
         Agent: AgentOrchestrator -> TechnicalAgent -> IntelAgent -> [RiskAgent] -> [SkillAgents] -> DecisionAgent
         Traditional: StockTrendAnalyzer (MA/MACD/RSI scoring)
      -> AnalysisResult assembly with dashboard JSON
      -> Persist to AnalysisHistory table
      -> Notification dispatch (multi-channel with md2img fallback)
```

### 4.2 Agent Execution Flow (Specialist Mode)

```
AgentOrchestrator._execute_pipeline()
  1. Build agent chain: Technical -> Intel -> Risk -> Skill(s) -> Decision
  2. For each agent:
     a. Build system prompt (agent-specific template + tool schema)
     b. Build user message (stock code + context + memory)
     c. Call run_agent_loop() -> ReAct cycle
     d. Post-process: Extract JSON opinion from raw text
     e. Store opinion in context.opinions[agent_name]
     f. Apply memory calibration to confidence
  3. Apply risk override: If RiskAgent flags hard veto, downgrade Decision signal
  4. Resolve final output: Graceful degradation if stages failed
  5. Normalize dashboard payload: Fill missing sections with defaults
```

### 4.3 ReAct Loop Flow

```
run_agent_loop(system_prompt, user_message, tools, max_steps)
  1. Build messages array [system, user]
  2. For step in range(max_steps):
     a. Call LLM (with tools schema)
     b. If response has tool_calls:
        - Execute tools (single or parallel batch via ThreadPoolExecutor)
        - Cache non-retriable results (normalized stock code key)
        - Append tool results to messages
        - Continue loop
     c. If response has content only:
        - Return content as final answer
  3. If max_steps exceeded, return last content or error
```

### 4.4 Portfolio Snapshot Replay Flow

```
get_portfolio_snapshot(account_id, as_of, cost_method)
  1. Load account metadata
  2. Query all events (cash_ledger, trades, corporate_actions) up to as_of date
  3. Sort events by (date, priority, id): cash(0) -> corp(1) -> trade(2)
  4. Replay events:
     - Cash: Update currency balance
     - Trade(buy): Deduct cash, add FIFO lot / update avg state
     - Trade(sell): Validate quantity, consume FIFO lots / avg position, compute realized PnL
     - Corp(cash_dividend): Add dividend to cash balance
     - Corp(split_adjustment): Multiply lot quantities, divide unit costs
  5. Build positions from remaining lots / avg state
  6. Fetch latest close prices for market value
  7. Convert all amounts to base currency via FX rates
  8. Persist snapshot to PortfolioSnapshot table
```

### 4.5 Backtest Evaluation Flow

```
BacktestService.run_backtest()
  1. Load candidate stocks from AnalysisHistory (untested records)
  2. For each candidate:
     a. Get forward bars from database (eval_window_days)
     b. BacktestEngine.evaluate_single()
        - Infer direction_expected from operation_advice
        - Infer position_recommendation (long/cash)
        - Classify outcome: win/loss/neutral
        - Evaluate stop-loss/take-profit targets
        - Determine first_hit and simulated exit
     c. Save BacktestResult record
  3. Recompute BacktestSummary (win_rate, direction_accuracy, etc.)
  4. Update AgentMemory calibration factors
```

### 4.6 Configuration Update Flow

```
SystemConfigService.update(items, config_version, reload_now)
  1. Validate config_version matches current (raise ConfigConflictError if stale)
  2. Collect field-level issues (type, range, enum, JSON, URL, SSRF)
  3. Collect cross-field issues (Telegram dependency, Feishu mode, LLM channel consistency)
  4. If errors: raise ConfigValidationError
  5. Normalize values (JSON compacting, sensitive key masking)
  6. Apply updates to .env file
  7. If reload_now:
     a. Config.reset_instance()
     b. Reset runtime singletons (DataFetcherManager, SearchService)
     c. setup_env(override=True)
     d. Run Config.validate() for runtime warnings
  8. Build explainability warnings (news window, MAX_WORKERS, startup-only keys)
```

### 4.7 Notification Dispatch Flow

```
NotificationService.send(content, email_send_to_all)
  1. Try markdown-to-image conversion (md2img)
  2. For each enabled channel:
     - Feishu: format_feishu_markdown() -> lark_md card -> fallback text
     - Telegram: _convert_to_telegram_markdown() -> chunked if > 4096 chars -> plain text fallback
     - WeChat: markdown/text type -> chunked if > max_bytes
     - Email: markdown_to_html_document() -> MIMEText with text+HTML alternatives
     - Discord/Slack: chunk_content_by_max_words/bytes -> Bot API or Webhook
     - Custom Webhook: Auto-detect DingTalk/Discord/Slack/Bark formats
  3. Merge with market review if applicable
  4. Save report to file
```

---

## 5. Common Modification Scenarios

### 5.1 Adding a New LLM Provider

**Files to modify**:
1. `src/agent/llm_adapter.py`: Add provider handling in `_parse_litellm_response()` if response format differs
2. `src/config.py`: Add provider to `SUPPORTED_LLM_CHANNEL_PROTOCOLS`, update `canonicalize_llm_channel_protocol()`
3. `src/core/config_registry.py`: Add field definitions for new provider channel fields

**Key functions**: `_parse_litellm_response()`, `resolve_llm_channel_protocol()`, `canonicalize_llm_channel_protocol()`

### 5.2 Adding a New Notification Channel

**Files to create/modify**:
1. Create `src/notification_sender/new_sender.py`: Implement `NewSender` class with `send_to_new(...)` method
2. Update `src/notification_sender/__init__.py`: Export the new class
3. `src/notification.py`: Add import, config check, and send path in `NotificationService`
4. `src/config.py`: Add configuration fields for the new channel

**Pattern to follow**: Each sender takes `Config` in constructor, checks `_is_configured()`, handles chunked sending for long content, returns bool.

### 5.3 Adding a New Agent Tool

**Files to modify**:
1. `src/agent/tools/data_tools.py` (or `analysis_tools.py`/`search_tools.py`): Implement function with `@tool` decorator
2. Update agent tool lists in the respective agent's `_get_tool_names()` method

**Decorator pattern**:
```python
@tool(name="my_tool", category="data", description="Tool description")
def my_tool(param1: str) -> dict:
    ...
```

### 5.4 Adding a New Trading Skill

**Files to create**:
1. Create YAML/Markdown skill file in `AGENT_SKILL_DIR`
2. Required fields: `name`, `display_name`, `description`, `instructions`, `category`, `core_rules`, `required_tools`
3. Optional: `market_regimes` for regime-based routing, `activation_conditions`

**Skill loading**: `SkillManager.load_skill_from_yaml()` or `load_skill_from_markdown()`

### 5.5 Adding a New Broker CSV Parser

**Files to modify**:
1. `src/services/portfolio_import_service.py`: Add `CsvParserSpec` to `DEFAULT_PARSER_SPECS` with column hint mappings

**Pattern**:
```python
CsvParserSpec(
    broker="new_broker",
    aliases=("alias1",),
    display_name="Broker Name",
    column_hints={
        "trade_date": ("Date", "Trade Date"),
        "symbol": ("Code", "Symbol"),
        "side": ("Direction", "Buy/Sell"),
        "quantity": ("Quantity", "Shares"),
        "price": ("Price", "Avg Price"),
        "trade_uid": ("Order ID",),
    },
)
```

### 5.6 Modifying the Decision Dashboard Schema

**Files to modify**:
1. `src/schemas/report_schema.py`: Update Pydantic models
2. `src/agent/agents/decision_agent.py`: Update system prompt JSON schema
3. `src/services/report_renderer.py`: Update Jinja2 template context
4. `src/services/history_service.py`: Update `_generate_single_stock_markdown()` if new dashboard sections

### 5.7 Adding a New Market Region

**Files to modify**:
1. `src/core/market_strategy.py`: Add new `MarketStrategyBlueprint` with region-specific strategy
2. `src/core/market_review.py`: Handle new region in `run_market_review()`
3. `src/core/market_profile.py`: Add MarketProfile for new region
4. `src/core/trading_calendar.py`: Add exchange calendar for new region
5. `data_provider/`: Add data fetcher support for new market

### 5.8 Modifying Agent Prompt Templates

**Files to modify**:
1. `src/agent/executor.py`: Contains `AGENT_SYSTEM_PROMPT`, `LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT`, etc.
2. Individual agent files in `src/agent/agents/`: `system_prompt()` method
3. `src/agent/factory.py`: `resolve_skill_prompt_state()` for skill injection

### 5.9 Changing Backtest Evaluation Logic

**Files to modify**:
1. `src/core/backtest_engine.py`: Modify `evaluate_single()`, `_classify_outcome()`, or `_evaluate_targets()`
2. `src/services/backtest_service.py`: Modify `run_backtest()` orchestration if needed

**Key design**: The engine is intentionally DB-agnostic and operates on plain values/protocols. To add new evaluation metrics, extend the return dict of `evaluate_single()` and the summary aggregation in `compute_summary()`.

### 5.10 Modifying Task Queue Concurrency

**Files to modify**:
1. `src/services/task_queue.py`: `AnalysisTaskQueue.sync_max_workers()` (already supports dynamic adjustment)
2. `src/config.py`: `max_workers` field

**Runtime behavior**: `sync_max_workers()` returns "applied" when idle, "deferred_busy" when tasks are inflight. The new value is applied immediately only when the queue is idle; otherwise it is deferred until the queue empties.

---

## Appendix: Key File Index

| Area | File | Purpose |
|------|------|---------|
| Pipeline | `D:/claude/daily_stock_analysis/src/core/pipeline.py` | Main analysis orchestrator |
| Agent Orchestrator | `D:/claude/daily_stock_analysis/src/agent/orchestrator.py` | Multi-agent coordination |
| ReAct Loop | `D:/claude/daily_stock_analysis/src/agent/runner.py` | Single ReAct implementation |
| LLM Adapter | `D:/claude/daily_stock_analysis/src/agent/llm_adapter.py` | Unified LiteLLM adapter |
| Tool Registry | `D:/claude/daily_stock_analysis/src/agent/tools/registry.py` | Tool registration & execution |
| Data Tools | `D:/claude/daily_stock_analysis/src/agent/tools/data_tools.py` | Market data tools |
| Analysis Tools | `D:/claude/daily_stock_analysis/src/agent/tools/analysis_tools.py` | Technical analysis tools |
| Search Tools | `D:/claude/daily_stock_analysis/src/agent/tools/search_tools.py` | News/intel search tools |
| Skill Base | `D:/claude/daily_stock_analysis/src/agent/skills/base.py` | Skill loading & management |
| Skill Router | `D:/claude/daily_stock_analysis/src/agent/skills/router.py` | Regime-based skill selection |
| Skill Agent | `D:/claude/daily_stock_analysis/src/agent/skills/skill_agent.py` | Single skill evaluation |
| Skill Aggregator | `D:/claude/daily_stock_analysis/src/agent/skills/aggregator.py` | Weighted consensus |
| Backtest Engine | `D:/claude/daily_stock_analysis/src/core/backtest_engine.py` | Pure-logic evaluation |
| Market Review | `D:/claude/daily_stock_analysis/src/core/market_review.py` | Daily market recap |
| Market Strategy | `D:/claude/daily_stock_analysis/src/core/market_strategy.py` | CN/US strategy blueprints |
| Trading Calendar | `D:/claude/daily_stock_analysis/src/core/trading_calendar.py` | Exchange calendar integration |
| Config | `D:/claude/daily_stock_analysis/src/config.py` | Central configuration |
| Analyzer | `D:/claude/daily_stock_analysis/src/analyzer.py` | GeminiAnalyzer + AnalysisResult |
| Storage | `D:/claude/daily_stock_analysis/src/storage.py` | DatabaseManager + ORM models |
| Notification | `D:/claude/daily_stock_analysis/src/notification.py` | Multi-channel dispatcher |
| Formatters | `D:/claude/daily_stock_analysis/src/formatters.py` | Markdown/HTML/Feishu converters |
| Report Language | `D:/claude/daily_stock_analysis/src/report_language.py` | i18n translation maps |
| Portfolio Service | `D:/claude/daily_stock_analysis/src/services/portfolio_service.py` | Account/trade/snapshot lifecycle |
| Portfolio Import | `D:/claude/daily_stock_analysis/src/services/portfolio_import_service.py` | Broker CSV parsing |
| Portfolio Risk | `D:/claude/daily_stock_analysis/src/services/portfolio_risk_service.py` | Concentration/drawdown/stop-loss |
| Analysis Service | `D:/claude/daily_stock_analysis/src/services/analysis_service.py` | Stock analysis wrapper |
| Task Queue | `D:/claude/daily_stock_analysis/src/services/task_queue.py` | Async task management + SSE |
| Task Service | `D:/claude/daily_stock_analysis/src/services/task_service.py` | Bot async analysis service |
| History Service | `D:/claude/daily_stock_analysis/src/services/history_service.py` | History queries + Markdown reports |
| Report Renderer | `D:/claude/daily_stock_analysis/src/services/report_renderer.py` | Jinja2 template rendering |
| System Config | `D:/claude/daily_stock_analysis/src/services/system_config_service.py` | .env management |
| Name Resolver | `D:/claude/daily_stock_analysis/src/services/name_to_code_resolver.py` | Name-to-code resolution |
| Import Parser | `D:/claude/daily_stock_analysis/src/services/import_parser.py` | CSV/Excel/clipboard parsing |
| Image Extractor | `D:/claude/daily_stock_analysis/src/services/image_stock_extractor.py` | Vision LLM code extraction |
| Social Sentiment | `D:/claude/daily_stock_analysis/src/services/social_sentiment_service.py` | Reddit/X/Polymarket data |
| Backtest Service | `D:/claude/daily_stock_analysis/src/services/backtest_service.py` | Backtest orchestration |
| Stock Service | `D:/claude/daily_stock_analysis/src/services/stock_service.py` | Realtime/history data API |
| Stock Code Utils | `D:/claude/daily_stock_analysis/src/services/stock_code_utils.py` | Code normalization |
| Agent Model Service | `D:/claude/daily_stock_analysis/src/services/agent_model_service.py` | Model deployment listing |
| History Comparison | `D:/claude/daily_stock_analysis/src/services/history_comparison_service.py` | Signal change tracking |
| Stock Mapping | `D:/claude/daily_stock_analysis/src/data/stock_mapping.py` | Static code->name mapping |
| Stock Index Loader | `D:/claude/daily_stock_analysis/src/data/stock_index_loader.py` | Frontend stock index loading |
| Analysis Metadata | `D:/claude/daily_stock_analysis/src/utils/analysis_metadata.py` | Selection source constants |
| Data Processing | `D:/claude/daily_stock_analysis/src/utils/data_processing.py` | JSON/data normalization |
| Email Sender | `D:/claude/daily_stock_analysis/src/notification_sender/email_sender.py` | SMTP email sending |
| Telegram Sender | `D:/claude/daily_stock_analysis/src/notification_sender/telegram_sender.py` | Telegram Bot API |
| Feishu Sender | `D:/claude/daily_stock_analysis/src/notification_sender/feishu_sender.py` | Feishu webhook |
| WeChat Sender | `D:/claude/daily_stock_analysis/src/notification_sender/wechat_sender.py` | Enterprise WeChat |
| Discord Sender | `D:/claude/daily_stock_analysis/src/notification_sender/discord_sender.py` | Discord webhook/bot |
| Slack Sender | `D:/claude/daily_stock_analysis/src/notification_sender/slack_sender.py` | Slack bot/webhook |
| Pushover Sender | `D:/claude/daily_stock_analysis/src/notification_sender/pushover_sender.py` | Pushover API |
| PushPlus Sender | `D:/claude/daily_stock_analysis/src/notification_sender/pushplus_sender.py` | PushPlus API |
| ServerChan3 Sender | `D:/claude/daily_stock_analysis/src/notification_sender/serverchan3_sender.py` | ServerChan3 API |
| AstrBot Sender | `D:/claude/daily_stock_analysis/src/notification_sender/astrbot_sender.py` | AstrBot API |
| Custom Webhook | `D:/claude/daily_stock_analysis/src/notification_sender/custom_webhook_sender.py` | Generic webhook |
