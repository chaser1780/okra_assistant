from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(r"F:\okra_assistant")
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


BASE_SETTINGS_TOML = """[project]
name = "okra-assistant"
timezone = "Asia/Shanghai"
language = "zh-CN"
currency = "CNY"

[providers.quotes]
name = "eastmoney_nav_api"
fallbacks = ["stale_snapshot"]
timeout_seconds = 15
history_page_size = 120
allow_stale_fallback = true

[providers.news]
name = "eastmoney_notice_and_articles"
timeout_seconds = 15
lookback_hours = 72
max_notices = 4
max_articles = 3

[providers.sentiment_news]
primary = "xueqiu_web"
fallbacks = ["douyin_web"]
timeout_seconds = 20
lookback_hours = 48
source_role = "sentiment_news"
allow_stale_fallback = true
health_threshold = "warning"
use_env_proxy = true
keyword_limit = 18
results_per_keyword = 6
xueqiu_cookie_file = "config/xueqiu_cookie.txt"
douyin_cookie_file = "config/douyin_cookie.txt"
xueqiu_browser = "edge"
xueqiu_profile = "Default"
xueqiu_profile_path = ""
douyin_browser = "edge"
douyin_profile = "Default"
douyin_profile_path = ""

[providers.intraday_proxy]
name = "sina_hq_proxy"
fallbacks = ["stale_snapshot"]
timeout_seconds = 20
allow_stale_fallback = true

[providers.estimated_nav]
name = "fundgz_1234567"
fallbacks = ["quote_nav_derived", "stale_snapshot"]
timeout_seconds = 30
allow_stale_fallback = true

[advice]
mode = "research"
risk_profile = "balanced"
holding_period = "medium_term"

[scoring]
day_change_weight = 5.0
month_change_weight = 1.8
high_volatility_penalty = 6.0
drawdown_alert_pct = -1.5

[scoring.impact_weights]
positive = 6.0
neutral = 0.0
negative = -8.0

[report]
output_format = "markdown"
top_news_per_fund = 2
include_risk_disclaimer = true
"""


BASE_STRATEGY_TOML = """[portfolio]
risk_profile = "balanced"
daily_max_trade_amount = 1000.0
cash_hub_floor = 100.0
min_position_value = 0.0
allow_full_exit = true
allow_fund_switch = true
accept_buy_the_dip = true
accept_trim_winners = true

[schedule]
intraday_start = "14:00"
intraday_end = "14:30"
nightly_start = "21:00"
nightly_end = "21:30"
run_if_missed_on_next_boot = true
report_mode = "intraday_proxy"

[core_dca]
amount_per_fund = 25.0
extra_buy_allowed = false

[tactical]
default_cap_value = 1000.0
min_add_amount = 100.0
mid_add_amount = 200.0
max_add_amount = 300.0
min_reduce_amount = 100.0
mid_reduce_amount = 200.0
max_reduce_amount = 300.0
max_actions_per_day = 3
proxy_weight = 8.0
nav_weight = 2.0
news_positive_weight = 3.0
news_negative_weight = -5.0
loss_rebound_bonus = 10.0
loss_rebound_return_threshold = -8.0
loss_rebound_proxy_threshold = 0.8
winner_trim_penalty = 12.0
winner_trim_return_pct = 5.0
winner_large_trim_return_pct = 8.0
winner_trim_proxy_threshold = -0.8
stale_proxy_penalty = 4.0
near_cap_penalty = 5.0
strong_add_score = 70.0
very_strong_add_score = 82.0
trim_score = 38.0
switch_out_score = 28.0

[manual_references]
use_yangjibao_board_heat = true
overrides_file = "market_overrides.json"

[allocation]
rebalance_band_pct = 5.0
max_single_theme_family_pct = 30.0
max_high_volatility_theme_pct = 45.0

[allocation.targets]
core_long_term = 50.0
satellite_mid_term = 20.0
tactical_short_term = 10.0
cash_defense = 20.0
"""


BASE_REVIEW_TOML = """[review]
enabled = true
horizons = [1, 5, 20]
compare_against = "validated_advice"
"""


BASE_AGENTS_TOML = """[orchestrator]
enabled = true
max_parallel_agents = 3
max_parallel_analysts = 3
max_parallel_researchers = 2
snapshot_enabled = true

[agents.market_analyst]
enabled = true
role = "analyst"
output_file = "market_analyst.json"

[agents.theme_analyst]
enabled = true
role = "analyst"
output_file = "theme_analyst.json"

[agents.fund_structure_analyst]
enabled = true
role = "analyst"
output_file = "fund_structure_analyst.json"

[agents.fund_quality_analyst]
enabled = true
role = "analyst"
output_file = "fund_quality_analyst.json"

[agents.news_analyst]
enabled = true
role = "analyst"
output_file = "news_analyst.json"

[agents.sentiment_analyst]
enabled = true
role = "analyst"
output_file = "sentiment_analyst.json"

[agents.bull_researcher]
enabled = true
role = "researcher"
output_file = "bull_researcher.json"

[agents.bear_researcher]
enabled = true
role = "researcher"
output_file = "bear_researcher.json"

[agents.research_manager]
enabled = true
role = "manager"
output_file = "research_manager.json"

[agents.risk_manager]
enabled = true
role = "manager"
output_file = "risk_manager.json"

[agents.portfolio_trader]
enabled = true
role = "manager"
output_file = "portfolio_trader.json"
"""


BASE_REALTIME_TOML = """[realtime]
enabled = true
provider = "fund_estimate_proxy"
enable_for_categories = ["etf_linked", "index_equity", "active_equity"]
confidence_threshold = 0.6
fallback_to_proxy = true
max_staleness_minutes = 20
"""


BASE_LLM_TOML = """model_provider = "OpenAI"
model = "gpt-5.4"
review_model = "gpt-5.4"
model_context_window = 1000000
model_auto_compact_token_limit = 900000
model_reasoning_effort = "xhigh"
disable_response_storage = true
network_access = "enabled"
windows_wsl_setup_acknowledged = true
preferred_auth_method = "apikey"
api_key_env = "OPENAI_API_KEY"
api_key_file = ""
personality = "friendly"

[model_providers.OpenAI]
name = "OpenAI"
base_url = "https://api.vip1129.cc"
wire_api = "responses"
requires_openai_auth = true
"""


BASE_PROJECT_TOML = """[project]
name = "okra-assistant"
display_name = "okra assistant"
version = "0.2.0"
status = "test"
created_at = "2026-03-13"
owner = "test"
language = "zh-CN"
platform = "windows-local"
entry_desktop = "app/web_api.py"
entry_intraday = "scripts/run_daily_pipeline.py"
entry_nightly = "scripts/run_daily_pipeline.py"

[paths]
project_root = "."
desktop_launcher = "run_desktop_app.ps1"
backup_dir = "backups"

[runtime]
python_executable = ""
"""


class TempAgentHome:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._setup()

    def _setup(self):
        for relative in [
            "config",
            "raw/quotes",
            "raw/news",
            "db/daily_scores",
            "db/intraday_proxies",
            "db/realtime_monitor",
            "db/portfolio_advice",
            "db/llm_context",
            "db/evidence_index",
            "db/llm_advice",
            "db/committee_advice",
            "db/llm_raw",
            "db/validated_advice",
            "db/agent_outputs",
            "db/agent_snapshots",
            "db/replay_experiments",
            "db/portfolio_state",
            "db/portfolio_state/snapshots",
            "db/review_results",
            "db/review_memory",
            "db/review_memory/cycles",
            "db/review_memory/permanent",
            "db/review_memory/user_confirmed",
            "db/review_memory/candidates",
            "db/review_memory/promotion_log",
            "db/long_memory",
            "db/long_memory/funds",
            "db/long_memory/market",
            "db/long_memory/market/regime_daily",
            "db/long_memory/execution",
            "db/long_memory/portfolio",
            "db/long_memory/candidates",
            "db/long_memory/approvals",
            "db/long_memory/exports",
            "db/daily_workspace",
            "db/execution_reviews",
            "db/trade_journal",
            "db/estimated_nav",
            "db/portfolio_valuation",
            "db/preflight",
            "reports/daily",
            "logs",
            "logs/llm",
            "logs/preflight",
            "logs/tasks",
            "temp",
            "cache",
        ]:
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        self.write_text("project.toml", BASE_PROJECT_TOML)
        self.write_text("config/settings.toml", BASE_SETTINGS_TOML)
        self.write_text("config/strategy.toml", BASE_STRATEGY_TOML)
        self.write_text("config/review.toml", BASE_REVIEW_TOML)
        self.write_text("config/agents.toml", BASE_AGENTS_TOML)
        self.write_text("config/realtime_valuation.toml", BASE_REALTIME_TOML)
        self.write_text("config/llm.toml", BASE_LLM_TOML)
        self.write_json("config/portfolio.json", {"portfolio_name": "测试组合", "funds": [], "as_of_date": ""})
        self.write_json("config/watchlist.json", {"funds": []})
        self.write_json("config/market_overrides.json", {"biases": []})
        self.write_json("db/review_memory/memory.json", {"updated_at": "", "lessons": [], "review_history": [], "bias_adjustments": [], "agent_feedback": []})

    def cleanup(self):
        self._tmp.cleanup()

    def write_json(self, relative: str, payload):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_text(self, relative: str, text: str):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_script(self, script_name: str, *args: str):
        env = os.environ.copy()
        env["FUND_AGENT_HOME"] = str(self.root)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, "-B", "-X", "utf8", str(SCRIPTS_DIR / script_name), "--agent-home", str(self.root), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
