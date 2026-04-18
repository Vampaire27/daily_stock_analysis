---
name: daily_stock_analysis-dr-data_provider
description: Use when working with the data_provider module of daily_stock_analysis — multi-source stock data fetching layer covering A-shares, HK stocks, US stocks, and US indices with automatic failover, circuit breakers, and rate limiting
---

# data_provider Module Deep-Read Reference

## 1. Module Purpose & Capabilities

The `data_provider` module is the **unified multi-source data fetching layer** for the daily_stock_analysis project. It implements the **Strategy Pattern** to manage seven different data sources (plus one market-review-only source), providing automatic failover, circuit breaking, rate limiting, and anti-ban strategies. It covers A-shares (Shanghai, Shenzhen, Beijing Stock Exchange), HK stocks, US stocks, and US indices.

### Core Capabilities

| Capability | Description | Primary Methods |
|---|---|---|
| Daily OHLCV data | Historical candlestick data with forward-adjusted prices | `get_daily_data()` |
| Realtime quotes | Live price, volume, PE/PB, market cap, turnover rate | `get_realtime_quote()` |
| Chip distribution | Cost distribution analysis (profit ratio, concentration) | `get_chip_distribution()` |
| Market statistics | Up/down counts, limit-up/down, total turnover | `get_market_stats()` |
| Sector rankings | Top/bottom performing industry sectors | `get_sector_rankings()` |
| Index quotes | Main market indices (CN: 6 indices, US: SPX/DJI/IXIC/VIX) | `get_main_indices()` |
| Stock names | Chinese stock name resolution with caching | `get_stock_name()` |
| Board membership | Industry/concept boards a stock belongs to | `get_belong_boards()` |
| Fundamental context | Valuation, growth, earnings, institution, capital flow, dragon-tiger | `get_fundamental_context()` |

### Public API Surface (DataFetcherManager)

The `DataFetcherManager` class in `base.py` is the **single entry point** consumers should use. Key public methods:

```python
manager = DataFetcherManager()

# Daily OHLCV data with automatic failover
df, source_name = manager.get_daily_data("600519", days=60)

# Realtime quote with configured source priority and field supplementation
quote = manager.get_realtime_quote("600519")  # returns UnifiedRealtimeQuote or None

# Chip distribution with circuit breaker
chip = manager.get_chip_distribution("600519")  # returns ChipDistribution or None

# Fundamental context (valuation + growth + earnings + institution + capital_flow + dragon_tiger + boards)
context = manager.get_fundamental_context("600519", budget_seconds=30)

# Market breadth statistics
stats = manager.get_market_stats()  # dict with up_count, down_count, limit_up_count, etc.

# Sector rankings
top, bottom = manager.get_sector_rankings(n=5)

# Index quotes
indices = manager.get_main_indices(region="cn")  # or "us"

# Stock name resolution (with multi-layer caching)
name = manager.get_stock_name("600519")

# Batch operations
names = manager.batch_get_stock_names(["600519", "000001"])
manager.prefetch_realtime_quotes(["600519", "000001", ...])
manager.prefetch_stock_names(["600519", ...])

# Cleanup
manager.close()
```

---

## 2. Core Design Logic

### Strategy Pattern Architecture

The module uses the Strategy Pattern with three layers:

1. **`BaseFetcher` (abstract base class)** in `base.py` -- defines the contract: `_fetch_raw_data()` and `_normalize_data()` are abstract; `get_daily_data()` is the concrete template method that chains fetch -> normalize -> clean -> calculate indicators.

2. **Concrete Fetchers** -- each data source implements the abstract methods:
   - `EfinanceFetcher` (Priority 0) -- Eastmoney via efinance library
   - `AkshareFetcher` (Priority 1) -- Eastmoney/Sina/Tencent via akshare library
   - `TushareFetcher` (Priority -1 when token configured, else 2) -- Tushare Pro API
   - `PytdxFetcher` (Priority 2) -- TongDaXin market servers
   - `BaostockFetcher` (Priority 3) -- Baostock free API
   - `YfinanceFetcher` (Priority 4) -- Yahoo Finance (US/HK fallback)
   - `LongbridgeFetcher` (Priority 5) -- Longbridge OpenAPI (US/HK final fallback)

3. **`DataFetcherManager`** -- orchestrates failover across fetchers sorted by priority.

### Why This Design

- **Resilience over perfection**: Each data source has unique failure modes (rate limits, IP bans, server downtime). The manager tries fetchers in priority order and switches on failure.
- **No hard dependency on any single provider**: If efinance gets banned, akshare picks up. If Tushare runs out of quota, others cover it.
- **Market-aware routing**: US stocks/indices are directly routed to YfinanceFetcher/LongbridgeFetcher, bypassing A-share-only fetchers. HK stocks route similarly.

### Priority Resolution

Priority is **dynamic**, not static:

```
With TUSHARE_TOKEN configured:
  TushareFetcher:    Priority -1 (highest, auto-promoted when token + API init succeed)
  EfinanceFetcher:   Priority 0
  AkshareFetcher:    Priority 1
  PytdxFetcher:      Priority 2
  BaostockFetcher:   Priority 3
  YfinanceFetcher:   Priority 4
  LongbridgeFetcher: Priority 5

Without TUSHARE_TOKEN:
  EfinanceFetcher:   Priority 0
  AkshareFetcher:    Priority 1
  TushareFetcher:    Priority 2 (unavailable, API is None)
  PytdxFetcher:      Priority 2
  BaostockFetcher:   Priority 3
  YfinanceFetcher:   Priority 4
  LongbridgeFetcher: Priority 5
```

All priorities are overridable via environment variables (e.g., `EFINANCE_PRIORITY=0`).

### Anti-Ban Strategy

Crawler-based fetchers (EfinanceFetcher, AkshareFetcher) implement multiple defense layers:

1. **Random jitter sleep** (2-5s for akshare, 1.5-3s for efinance) between requests
2. **User-Agent rotation** from a pool of 5 browser UAs
3. **Exponential backoff retry** via tenacity (up to 3 attempts)
4. **Circuit breaker** (see below) to stop hammering failing sources
5. **Request-level timeout** for efinance calls (default 30s, env `EFINANCE_CALL_TIMEOUT`)

### Circuit Breaker Pattern

Two global circuit breakers in `realtime_types.py`:

| Breaker | Failure Threshold | Cooldown | Purpose |
|---|---|---|---|
| `_realtime_circuit_breaker` | 3 failures | 300s (5min) | Realtime quote endpoints |
| `_chip_circuit_breaker` | 2 failures | 600s (10min) | Chip distribution endpoints (more conservative) |

State machine: `CLOSED` (normal) --N failures--> `OPEN` (blocked) --cooldown--> `HALF_OPEN` (probe) --success--> `CLOSED` / --failure--> `OPEN`

### Realtime Quote Field Supplementation

The manager implements **cross-source field supplementation**: when the first successful data source returns a quote with missing fields (volume_ratio, turnover_rate, PE/PB ratios, market caps, amplitude), subsequent sources in the priority chain are queried to fill in the gaps. Maximum 1 supplement attempt after the primary source succeeds.

### Fail-Open Fundamental Pipeline

The `AkshareFundamentalAdapter` uses capability probing across multiple AkShare endpoint candidates. It never raises to the caller -- partial data is always allowed. Each fundamental block (valuation, growth, earnings, institution, capital_flow, dragon_tiger, boards) is independently fetched with its own timeout budget.

---

## 3. Core Data Structures

### STANDARD_COLUMNS (`base.py`, line 36)

```python
STANDARD_COLUMNS = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
```

All fetchers normalize their raw output to these 8 columns plus a `code` column.

### UnifiedRealtimeQuote (`realtime_types.py`, line 108)

The universal realtime quote dataclass. All fetchers return this type (or None on failure).

| Field | Type | Description |
|---|---|---|
| `code` | str | Stock code |
| `name` | str | Stock name |
| `source` | RealtimeSource | Data source enum |
| `price` | Optional[float] | Latest price |
| `change_pct` | Optional[float] | Change percentage |
| `change_amount` | Optional[float] | Change amount |
| `volume` | Optional[int] | Volume (in shares, not lots) |
| `amount` | Optional[float] | Turnover amount (CNY) |
| `volume_ratio` | Optional[float] | Volume ratio |
| `turnover_rate` | Optional[float] | Turnover rate (%) |
| `amplitude` | Optional[float] | Amplitude (%) |
| `open_price` | Optional[float] | Open price |
| `high` | Optional[float] | Day high |
| `low` | Optional[float] | Day low |
| `pre_close` | Optional[float] | Previous close |
| `pe_ratio` | Optional[float] | P/E ratio (dynamic) |
| `pb_ratio` | Optional[float] | P/B ratio |
| `total_mv` | Optional[float] | Total market cap (CNY) |
| `circ_mv` | Optional[float] | Circulating market cap (CNY) |
| `change_60d` | Optional[float] | 60-day change (%) |
| `high_52w` | Optional[float] | 52-week high |
| `low_52w` | Optional[float] | 52-week low |

Key methods: `to_dict()`, `has_basic_data()`, `has_volume_data()`

### ChipDistribution (`realtime_types.py`, line 181)

| Field | Type | Description |
|---|---|---|
| `code` | str | Stock code |
| `date` | str | Date string |
| `profit_ratio` | float | Profit ratio (0-1) |
| `avg_cost` | float | Average cost |
| `cost_90_low/high` | float | 90% chip cost range |
| `concentration_90` | float | 90% concentration (lower = more concentrated) |
| `cost_70_low/high` | float | 70% chip cost range |
| `concentration_70` | float | 70% concentration |

Key method: `get_chip_status(current_price)` returns a Chinese description of chip state.

### RealtimeSource Enum (`realtime_types.py`, line 94)

```python
class RealtimeSource(Enum):
    EFINANCE = "efinance"
    AKSHARE_EM = "akshare_em"
    AKSHARE_SINA = "akshare_sina"
    AKSHARE_QQ = "akshare_qq"
    TUSHARE = "tushare"
    TENCENT = "tencent"
    SINA = "sina"
    STOOQ = "stooq"          # US stock fallback
    LONGBRIDGE = "longbridge" # US/HK fallback
    FALLBACK = "fallback"
```

### CircuitBreaker (`realtime_types.py`, line 270)

States: `CLOSED`, `OPEN`, `HALF_OPEN`

Key methods: `is_available(source)`, `record_success(source)`, `record_failure(source, error)`, `record_inconclusive(source)`, `reset(source)`, `get_status()`

### Exception Classes (`base.py`, lines 225-237)

```python
class DataFetchError(Exception):     # Base data fetch exception
class RateLimitError(DataFetchError):  # Rate limit / quota exceeded
class DataSourceUnavailableError(DataFetchError):  # Data source unavailable
```

### Market Detection Helpers (`base.py`)

| Function | Location | Purpose |
|---|---|---|
| `normalize_stock_code(code)` | base.py:66 | Strip exchange prefixes (SH/SZ/BJ/HK), normalize HK to `HK00700` format |
| `canonical_stock_code(code)` | base.py:208 | Uppercase for display/storage |
| `is_bse_code(code)` | base.py:167 | Detect Beijing Stock Exchange (92xxxx, 43xxxx, 83xxxx, etc.) |
| `is_st_stock(name)` | base.py:187 | Detect ST stocks (contains "ST") |
| `is_kc_cy_stock(code)` | base.py:196 | Detect STAR Market (688xxx) or ChiNext (300xxx) |
| `_is_hk_market(code)` | base.py:130 | Detect HK market (HK prefix, .HK suffix, or 5-digit code) |
| `_is_us_market(code)` | base.py:122 | Detect US market via us_index_mapping |
| `_is_etf_code(code)` | base.py:148 | Detect ETF codes (51/52/56/58/15/16/18 prefixes) |
| `_market_tag(code)` | base.py:158 | Return "cn", "us", or "hk" |

### US Index Mapping (`us_index_mapping.py`)

```python
US_INDEX_MAPPING = {
    'SPX': ('^GSPC', '标普500指数'),
    'DJI': ('^DJI', '道琼斯工业指数'),
    'IXIC': ('^IXIC', '纳斯达克综合指数'),
    'NDX': ('^NDX', '纳斯达克100指数'),
    'VIX': ('^VIX', 'VIX恐慌指数'),
    'RUT': ('^RUT', '罗素2000指数'),
}
```

Functions: `is_us_index_code()`, `is_us_stock_code()`, `get_us_index_yf_symbol()`

---

## 4. State Flow

### Daily Data Flow

```
Caller: manager.get_daily_data("600519", days=60)
    |
    v
DataFetcherManager.get_daily_data()
    |
    +-- normalize_stock_code("600519")  => "600519"
    +-- Market detection: _is_us_market? _is_hk_market?
    |
    +-- US stock? => Direct route to YfinanceFetcher or LongbridgeFetcher
    |
    +-- Otherwise: iterate fetchers by priority:
         |
         v
      For each fetcher (sorted by priority):
         |
         +-- BaseFetcher.get_daily_data()  [template method]
              |
              +-- _fetch_raw_data()       [abstract -- subclass implements]
              |      |
              |      +-- Rate limit check / sleep
              |      +-- API call (akshare/efinance/tushare/etc.)
              |      +-- Return raw DataFrame
              |
              +-- _normalize_data()       [abstract -- subclass implements]
              |      |
              |      +-- Column rename mapping -> STANDARD_COLUMNS
              |      +-- Add 'code' column
              |
              +-- _clean_data()           [concrete in BaseFetcher]
              |      |
              |      +-- Convert date to datetime
              |      +-- Coerce numeric columns
              |      +-- Drop rows with NaN close/volume
              |      +-- Sort by date ascending
              |
              +-- _calculate_indicators() [concrete in BaseFetcher]
                     |
                     +-- MA5, MA10, MA20
                     +-- volume_ratio (daily volume / 5-day avg, shifted)
         |
         +-- Success? Return (df, fetcher.name)
         +-- Failure? Log error, try next fetcher
         |
    v
All failed => raise DataFetchError with summary of all failures
```

### Realtime Quote Flow

```
Caller: manager.get_realtime_quote("600519")
    |
    v
DataFetcherManager.get_realtime_quote()
    |
    +-- Check config.enable_realtime_quote (skip if disabled)
    +-- normalize_stock_code()
    |
    +-- US/HK stock? => Special dual-source routing:
    |      Primary: Longbridge (if configured) or Yfinance
    |      Secondary: the other one as fallback
    |      Supplement missing fields between sources
    |
    +-- A-share? => Iterate configured realtime_source_priority:
           "efinance" => EfinanceFetcher.get_realtime_quote()
           "akshare_em" => AkshareFetcher.get_realtime_quote(source="em")
           "akshare_sina" => AkshareFetcher.get_realtime_quote(source="sina")
           "tencent" => AkshareFetcher.get_realtime_quote(source="tencent")
           "tushare" => TushareFetcher.get_realtime_quote()
           |
           +-- First source with has_basic_data() => primary_quote
           +-- Continue to supplement missing _SUPPLEMENT_FIELDS:
               volume_ratio, turnover_rate, pe_ratio, pb_ratio,
               total_mv, circ_mv, amplitude
           +-- Max 1 supplement attempt
    |
    v
Return UnifiedRealtimeQuote or None
```

### Chip Distribution Flow

```
Caller: manager.get_chip_distribution("600519")
    |
    v
DataFetcherManager.get_chip_distribution()
    |
    +-- Check config.enable_chip_distribution
    +-- Get _chip_circuit_breaker
    |
    +-- Iterate fetchers by priority:
         +-- Skip if no get_chip_distribution method
         +-- Check circuit breaker (source_key = "{name}_chip")
         +-- Call fetcher.get_chip_distribution()
         +-- Success? record_success, return ChipDistribution
         +-- None result? record_inconclusive (releases HALF_OPEN slot)
         +-- Exception? record_failure, continue to next
    |
    v
All failed => return None
```

### Fundamental Context Flow

```
Caller: manager.get_fundamental_context("600519", budget_seconds=30)
    |
    v
DataFetcherManager.get_fundamental_context()
    |
    +-- Check config.enable_fundamental_pipeline
    +-- Market detection: US/HK => not_supported
    +-- Check cache (TTL + max entries configurable)
    |
    +-- Stage 1: Valuation block (from realtime_quote)
    |      pe_ratio, pb_ratio, total_mv, circ_mv
    |
    +-- Stage 2: Growth/Earnings/Institution bundle (one AkShare call)
    |      Via AkshareFundamentalAdapter.get_fundamental_bundle()
    |      - Financial indicators (revenue_yoy, profit_yoy, ROE, gross_margin)
    |      - Earnings forecast/quick report
    |      - Dividend details (TTM cash dividend per share)
    |      - Institution holding changes
    |      - Top 10 shareholder changes
    |
    +-- Stage 3: Capital flow block
    |      Via AkshareFundamentalAdapter.get_capital_flow()
    |      - Stock net inflow (main force, 5d, 10d)
    |      - Sector fund flow rankings
    |
    +-- Stage 4: Dragon tiger block
    |      Via AkshareFundamentalAdapter.get_dragon_tiger_flag()
    |      - is_on_list, recent_count, latest_date
    |
    +-- Stage 5: Boards block
    |      Via get_board_context() -> _get_sector_rankings_with_meta()
    |
    +-- Each stage respects remaining budget_seconds
    +-- Each stage uses _run_with_retry with thread-based timeout
    +-- All blocks are fail-open: partial data allowed
    |
    +-- Cache result if _should_cache_fundamental_context() returns True
    |
    v
Return dict with status ("ok"/"partial"/"failed"/"not_supported") per block
```

### Error Handling Patterns

1. **Per-fetcher retry**: All `_fetch_raw_data` methods use `@retry` from tenacity with exponential backoff (stop_after_attempt=3, wait_exponential(multiplier=1, min=2, max=30)).
2. **Manager-level failover**: When a fetcher raises any exception, the manager logs the error and tries the next fetcher.
3. **Rate limit detection**: Each fetcher detects rate limit keywords in error messages and raises `RateLimitError`.
4. **Circuit breaker**: For realtime and chip endpoints, the circuit breaker prevents repeated calls to failing sources.
5. **Graceful degradation**: Returns `None` (not exception) for realtime quotes, chip distribution, and fundamental blocks when all sources fail.

---

## 5. Common Modification Scenarios

### Scenario 1: Add a new data source

**What to modify:**

1. Create a new file `data_provider/your_new_fetcher.py` that extends `BaseFetcher` from `data_provider/base.py`.
2. Implement the abstract methods:
   - `_fetch_raw_data(stock_code, start_date, end_date) -> pd.DataFrame`
   - `_normalize_data(df, stock_code) -> pd.DataFrame` (map columns to STANDARD_COLUMNS)
3. Optionally override: `get_realtime_quote()`, `get_chip_distribution()`, `get_stock_name()`, `get_stock_list()`, `get_main_indices()`, `get_market_stats()`, `get_sector_rankings()`, `get_belong_board()`.
4. Set `name` class attribute and `priority` class attribute (or make it configurable via env var).
5. Register in `DataFetcherManager._init_default_fetchers()` (`base.py`, line 844): import and instantiate your fetcher, add to the `self._fetchers` list.
6. Register in `data_provider/__init__.py` exports.
7. If the new source provides realtime quotes, add it to the `realtime_source_priority` config handling in `DataFetcherManager.get_realtime_quote()` and to the `bulk_sources` list in `prefetch_realtime_quotes()`.
8. If it provides realtime quotes, ensure the circuit breaker key naming follows the pattern in `get_chip_distribution()`.

### Scenario 2: Change realtime quote source priority

**What to modify:**

The priority is controlled by the `realtime_source_priority` config option (from `src.config.get_config()`). Default is typically `"efinance,akshare_em,akshare_sina,tencent,tushare"`.

To change the order without code changes: set the `REALTIME_SOURCE_PRIORITY` environment variable or update the config file.

To add a new realtime source to the routing logic, modify the source matching loop in `DataFetcherManager.get_realtime_quote()` (`base.py`, around line 1205). Each source type has an `elif` block that finds the matching fetcher and calls its `get_realtime_quote()` method.

### Scenario 3: Add new columns to STANDARD_COLUMNS

**What to modify:**

1. Update `STANDARD_COLUMNS` in `data_provider/base.py` (line 36).
2. Update `_normalize_data()` in **every** fetcher to map their source-specific columns to the new standard column name.
3. Update `_calculate_indicators()` in `BaseFetcher` if the new column needs derived calculations.
4. Update `_clean_data()` in `BaseFetcher` if the new column needs type coercion or cleaning.

**Affected files:**
- `data_provider/base.py` (STANDARD_COLUMNS definition, _calculate_indicators, _clean_data)
- `data_provider/efinance_fetcher.py` (_normalize_data)
- `data_provider/akshare_fetcher.py` (_normalize_data)
- `data_provider/tushare_fetcher.py` (_normalize_data)
- `data_provider/pytdx_fetcher.py` (_normalize_data)
- `data_provider/baostock_fetcher.py` (_normalize_data)
- `data_provider/yfinance_fetcher.py` (_normalize_data)
- `data_provider/longbridge_fetcher.py` (_normalize_data)

### Scenario 4: Adjust rate limiting / anti-ban parameters

**What to modify:**

- **EfinanceFetcher**: Constructor params `sleep_min` (default 1.5) and `sleep_max` (default 3.0) in `data_provider/efinance_fetcher.py`, line 258.
- **AkshareFetcher**: Constructor params `sleep_min` (default 2.0) and `sleep_max` (default 5.0) in `data_provider/akshare_fetcher.py`, line 270.
- **TushareFetcher**: `rate_limit_per_minute` (default 80) in `data_provider/tushare_fetcher.py`, line 133. Controls the per-minute call counter.
- **Retry attempts**: Change `stop=stop_after_attempt(N)` in the `@retry` decorator on each fetcher's `_fetch_raw_data` method.
- **Efinance call timeout**: Environment variable `EFINANCE_CALL_TIMEOUT` (default 30s), read in `data_provider/efinance_fetcher.py`, line 46.

### Scenario 5: Add support for a new market (e.g., Japanese stocks)

**What to modify:**

1. Add a `_is_jp_market(code)` helper in `data_provider/base.py` following the pattern of `_is_hk_market()` and `_is_us_market()`.
2. Update `_market_tag()` in `base.py` to return "jp" for Japanese codes.
3. Create a new fetcher or extend an existing one (e.g., YfinanceFetcher already supports JP stocks via `.T` suffix) to handle the market.
4. Update `DataFetcherManager.get_daily_data()` to add routing logic for "jp" market codes.
5. Update `DataFetcherManager.get_realtime_quote()` similarly.
6. Update `normalize_stock_code()` if JP codes need special normalization.
7. Update `get_fundamental_context()` to handle the new market (currently returns `not_supported` for non-CN markets).

### Scenario 6: Change the circuit breaker thresholds

**What to modify:**

In `data_provider/realtime_types.py`, lines 428-438:

```python
_realtime_circuit_breaker = CircuitBreaker(
    failure_threshold=3,      # Change this to adjust failure count before circuit opens
    cooldown_seconds=300.0,   # Change this to adjust cooldown duration
    half_open_max_calls=1
)

_chip_circuit_breaker = CircuitBreaker(
    failure_threshold=2,      # Change this for chip distribution
    cooldown_seconds=600.0,   # Change this for chip cooldown
    half_open_max_calls=1
)
```

To make these configurable, you would need to refactor the global instances into factory functions that read from config, or pass them as constructor parameters to the relevant methods.
