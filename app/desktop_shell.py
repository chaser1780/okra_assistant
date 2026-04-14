from __future__ import annotations

import argparse
import json
import sys
import threading
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

try:
    from decision_support import build_agent_stage_snapshot, stage_label, summarize_fund_agent_signals
    from task_runtime import run_streaming_command
    from task_state import (
        TASK_CARD_SPECS,
        begin_task_status,
        build_task_card_text,
        current_task_result_info,
        finish_task_status,
        finished_hint_text,
        initial_task_status,
        interpret_run_output_line,
        running_hint_text,
        update_task_elapsed,
        update_task_step,
    )
    from theme import SPACING, THEME, TYPOGRAPHY, configure_theme
    from ui_prefs import load_ui_state, save_ui_state
    from ui_schema_overrides import (
        build_dashboard_detail_schema,
        build_fund_detail_schema,
        build_portfolio_actions_schema,
        build_portfolio_report_schema,
        build_portfolio_strategy_schema,
        build_portfolio_cockpit_schema,
        build_realtime_detail_schema,
        build_trade_precheck_schema,
    )
    from ui_schemas import (
        build_agent_detail_schema,
        build_review_summary_schema,
        build_system_schema,
        build_trade_history_schema,
    )
    from ui_support import (
        build_action_change_lines,
        build_dashboard_alerts,
        build_auto_realtime_status_text,
        build_pipeline_command,
        build_plain_language_summary,
        build_preflight_command,
        build_realtime_command,
        build_realtime_row_values,
        build_realtime_summary_text,
        build_review_detail_fallback,
        build_trade_command,
        build_runtime_env,
        desktop_log_path,
        fix_text,
        historical_operating_metrics,
        load_state,
        load_validated_for_date,
        money,
        num,
        open_path,
        pct,
        previous_date,
        should_resume_intraday,
        should_resume_nightly,
        summarize_state as summarize,
        today_str,
    )
    from views.dashboard import build_dashboard_view
    from views.portfolio import build_portfolio_view
    from views.realtime import build_realtime_view
    from views.research import build_agents_view, build_research_view
    from views.review import build_review_view
    from views.runtime import build_runtime_view
    from views.settings import build_settings_view
    from views.trade import build_trade_view
    from widgets import ToastHub, WheelCombobox, create_empty_state, make_badge
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from decision_support import build_agent_stage_snapshot, stage_label, summarize_fund_agent_signals
    from task_runtime import run_streaming_command
    from task_state import (
        TASK_CARD_SPECS,
        begin_task_status,
        build_task_card_text,
        current_task_result_info,
        finish_task_status,
        finished_hint_text,
        initial_task_status,
        interpret_run_output_line,
        running_hint_text,
        update_task_elapsed,
        update_task_step,
    )
    from theme import SPACING, THEME, TYPOGRAPHY, configure_theme
    from ui_prefs import load_ui_state, save_ui_state
    from ui_schema_overrides import (
        build_dashboard_detail_schema,
        build_fund_detail_schema,
        build_portfolio_actions_schema,
        build_portfolio_report_schema,
        build_portfolio_strategy_schema,
        build_portfolio_cockpit_schema,
        build_realtime_detail_schema,
        build_trade_precheck_schema,
    )
    from ui_schemas import (
        build_agent_detail_schema,
        build_review_summary_schema,
        build_system_schema,
        build_trade_history_schema,
    )
    from ui_support import (
        build_action_change_lines,
        build_dashboard_alerts,
        build_auto_realtime_status_text,
        build_pipeline_command,
        build_plain_language_summary,
        build_preflight_command,
        build_realtime_command,
        build_realtime_row_values,
        build_realtime_summary_text,
        build_review_detail_fallback,
        build_trade_command,
        build_runtime_env,
        desktop_log_path,
        fix_text,
        historical_operating_metrics,
        load_state,
        load_validated_for_date,
        money,
        num,
        open_path,
        pct,
        previous_date,
        should_resume_intraday,
        should_resume_nightly,
        summarize_state as summarize,
        today_str,
    )
    from views.dashboard import build_dashboard_view
    from views.portfolio import build_portfolio_view
    from views.realtime import build_realtime_view
    from views.research import build_agents_view, build_research_view
    from views.review import build_review_view
    from views.runtime import build_runtime_view
    from views.settings import build_settings_view
    from views.trade import build_trade_view
    from widgets import ToastHub, WheelCombobox, create_empty_state, make_badge

sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "scripts")))
from config_mutations import remove_watchlist_item, update_fund_cap_value, update_strategy_controls, upsert_watchlist_item
from portfolio_exposure import analyze_portfolio_exposure
from trade_constraints import build_trade_constraints


APP_TITLE = "okra 的小助手"
DEFAULT_AGENT_HOME = Path(r"F:\okra_assistant")
AUTO_REALTIME_REFRESH_MS = 5 * 60 * 1000
AUTO_REALTIME_RETRY_MS = 60 * 1000
VIEW_MODE_LABELS = {"analyst": "分析师视角", "investor": "投资用户视角"}
TAB_LABELS = {
    "dash": {"analyst": "总览", "investor": "今天"},
    "portfolio": {"analyst": "组合策略", "investor": "配置"},
    "research": {"analyst": "研究建议", "investor": "动作"},
    "trade": {"analyst": "交易执行", "investor": "交易执行"},
    "review": {"analyst": "复盘记忆", "investor": "复盘"},
    "rt": {"analyst": "实时监控", "investor": "实时监控"},
    "agents": {"analyst": "智能体", "investor": "智能体"},
    "runtime": {"analyst": "运行", "investor": "运行"},
    "settings": {"analyst": "设置数据", "investor": "设置数据"},
}
TAB_LAYOUTS = {
    "investor": ["dash", "portfolio", "research", "trade", "review", "rt", "agents", "runtime", "settings"],
    "analyst": ["dash", "portfolio", "research", "trade", "review", "rt", "agents", "runtime", "settings"],
}
SIDEBAR_TAB_GLYPHS = {
    "dash": "◈",
    "portfolio": "▣",
    "research": "◆",
    "trade": "◉",
    "review": "◎",
    "rt": "◌",
    "agents": "◍",
    "runtime": "▤",
    "settings": "◫",
}
LEGACY_TAB_TO_KEY = {
    "总览": "dash",
    "首页": "dash",
    "今天": "dash",
    "组合策略": "portfolio",
    "组合": "portfolio",
    "配置": "portfolio",
    "研究建议": "research",
    "今日动作": "research",
    "动作": "research",
    "交易执行": "trade",
    "复盘记忆": "review",
    "复盘": "review",
    "实时监控": "rt",
    "智能体": "agents",
    "运行": "runtime",
    "设置数据": "settings",
}


def _bucket_label(bucket: str) -> str:
    return {
        "core_long_term": "长期核心仓",
        "satellite_mid_term": "中期卫星仓",
        "tactical_short_term": "短期战术仓",
        "cash_defense": "防守/现金仓",
    }.get(bucket, bucket or "未分类")


class App:
    def __init__(self, home: Path, selected: str | None = None):
        self.home = home
        self.state = load_state(home, selected)
        self.ui_state = load_ui_state(home)
        self.busy = False
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = max(1320, min(1660, screen_w - 90))
        height = max(860, min(1040, screen_h - 100))
        self.root.geometry(f"{width}x{height}+36+28")
        self.root.minsize(1220, 820)
        self.root.option_add("*Font", "{Microsoft YaHei UI} 10")
        self.root.option_add("*Listbox.font", "{Microsoft YaHei UI} 10")
        self.root.option_add("*Text.font", "{Microsoft YaHei UI} 10")

        self._ui_save_job = None
        self.closing = False
        self.auto_realtime_job_id = None
        self.auto_realtime_next_at = None
        self.active_job_name = ""
        self.active_task_kind = ""
        self.active_task_date = ""
        self.active_job_started_at = None

        self._init_vars()
        self.view_mode_var = tk.StringVar(value=VIEW_MODE_LABELS["analyst"])
        if self.rt_status_filter_var.get().strip() not in {"全部状态", "正常", "陈旧"}:
            self.rt_status_filter_var.set("全部状态")
        if self.rt_mode_filter_var.get().strip() not in {"全部模式", "estimate", "proxy", "official"}:
            self.rt_mode_filter_var.set("全部模式")
        if self.rt_sort_var.get().strip() not in {"今日收益", "涨跌幅", "估值-代理分歧", "仓位占比", "异常程度", "可信度", "估算模式", "数据时效", "基金名称", "角色"}:
            self.rt_sort_var.set("异常程度")
        self._init_runtime_state()
        if self.rt_sort_key not in {"fund", "role", "pnl", "pct", "divergence", "weight", "anomaly", "confidence", "mode", "fresh"}:
            self.rt_sort_key = "anomaly"
            self.rt_sort_desc = True
        self.build()
        self.refresh()
        self.root.after(120, self.startup_realtime_refresh)

    def _init_vars(self):
        self.date_var = tk.StringVar(value=self.state["selected_date"])
        self.trade_date_var = tk.StringVar(value=self.state["selected_date"])
        self.trade_fund_var = tk.StringVar()
        self.trade_suggestion_var = tk.StringVar()
        self.trade_action_var = tk.StringVar(value="buy")
        self.trade_amount_var = tk.StringVar(value="100")
        self.trade_nav_var = tk.StringVar()
        self.trade_units_var = tk.StringVar()
        self.settings_risk_profile_var = tk.StringVar()
        self.settings_cash_floor_var = tk.StringVar()
        self.settings_gross_limit_var = tk.StringVar()
        self.settings_net_limit_var = tk.StringVar()
        self.settings_dca_amount_var = tk.StringVar()
        self.settings_report_mode_var = tk.StringVar(value="intraday_proxy")
        self.settings_core_target_var = tk.StringVar()
        self.settings_satellite_target_var = tk.StringVar()
        self.settings_tactical_target_var = tk.StringVar()
        self.settings_defense_target_var = tk.StringVar()
        self.settings_rebalance_band_var = tk.StringVar()
        self.settings_cap_fund_var = tk.StringVar()
        self.settings_cap_value_var = tk.StringVar()
        self.watchlist_code_var = tk.StringVar()
        self.watchlist_name_var = tk.StringVar()
        self.watchlist_category_var = tk.StringVar(value="active_equity")
        self.watchlist_benchmark_var = tk.StringVar()
        self.watchlist_risk_var = tk.StringVar(value="high")
        self.research_search_var = tk.StringVar(value=self.ui_state.get("filters", {}).get("research_search", ""))
        self.research_action_filter_var = tk.StringVar(value=self.ui_state.get("filters", {}).get("research_action", "全部动作"))
        self.research_status_filter_var = tk.StringVar(value=self.ui_state.get("filters", {}).get("research_status", "全部状态"))
        self.agent_search_var = tk.StringVar(value=self.ui_state.get("filters", {}).get("agent_search", ""))
        self.agent_status_filter_var = tk.StringVar(value=self.ui_state.get("filters", {}).get("agent_status", "全部状态"))
        self.rt_search_var = tk.StringVar(value=self.ui_state.get("filters", {}).get("rt_search", ""))
        self.rt_status_filter_var = tk.StringVar(value=self.ui_state.get("filters", {}).get("rt_status", "全部状态"))
        self.rt_mode_filter_var = tk.StringVar(value=self.ui_state.get("filters", {}).get("rt_mode", "全部模式"))
        self.rt_sort_var = tk.StringVar(value=self.ui_state.get("filters", {}).get("rt_sort", "盈亏绝对值"))
        self.review_source_filter_var = tk.StringVar(value=self.ui_state.get("filters", {}).get("review_source", "全部来源"))
        self.review_horizon_filter_var = tk.StringVar(value=self.ui_state.get("filters", {}).get("review_horizon", "全部周期"))
        self.watchlist_search_var = tk.StringVar(value=self.ui_state.get("filters", {}).get("watchlist_search", ""))
        self.watchlist_category_filter_var = tk.StringVar(value=self.ui_state.get("filters", {}).get("watchlist_category", "全部类别"))
        self.watchlist_risk_filter_var = tk.StringVar(value=self.ui_state.get("filters", {}).get("watchlist_risk", "全部风险"))

        self.hero_selected_var = tk.StringVar(value="查看日")
        self.hero_context_var = tk.StringVar(value="今日链路状态：等待数据载入。")
        self.runtime_banner_var = tk.StringVar(value="运行控制台：等待任务调度。")
        self.research_meta_var = tk.StringVar(value="等待建议载入。")
        self.agents_meta_var = tk.StringVar(value="等待智能体摘要载入。")
        self.portfolio_meta_var = tk.StringVar(value="等待组合结构与策略目标载入。")
        self.review_meta_var = tk.StringVar(value="等待复盘结果载入。")
        self.trade_meta_var = tk.StringVar(value="录入交易后将同步回写持仓。")
        self.settings_meta_var = tk.StringVar(value="管理策略、观察池与系统健康。")
        self.status_var = tk.StringVar(value="就绪")
        self.run_hint_var = tk.StringVar(value="当前没有运行中的任务。")
        self.run_step_var = tk.StringVar(value="当前步骤：—")
        self.auto_realtime_var = tk.StringVar(value="自动刷新：启动后将立即刷新。")

        self.dash_cards = {
            "action_title": tk.StringVar(value="今日主动作"),
            "action_value": tk.StringVar(value="暂无"),
            "action_body": tk.StringVar(value="等待日内建议生成。"),
            "market_title": tk.StringVar(value="市场状态"),
            "market_value": tk.StringVar(value="暂无"),
            "market_body": tk.StringVar(value="等待市场摘要。"),
            "confidence_title": tk.StringVar(value="可信度横幅"),
            "confidence_value": tk.StringVar(value="暂无"),
            "confidence_body": tk.StringVar(value="等待建议链路结果。"),
            "risk_title": tk.StringVar(value="风险提醒"),
            "risk_value": tk.StringVar(value="暂无"),
            "risk_body": tk.StringVar(value="等待组合与告警信息。"),
        }
        self.dash_plan_cards = {
            "do_title": tk.StringVar(value="今天要做"),
            "do_body": tk.StringVar(value="等待今日建议生成。"),
            "wait_title": tk.StringVar(value="今天可以等"),
            "wait_body": tk.StringVar(value="等待观察项整理。"),
            "avoid_title": tk.StringVar(value="今天不建议做"),
            "avoid_body": tk.StringVar(value="等待风险提醒整理。"),
        }
        self.rt_cards = {
            "snapshot_title": tk.StringVar(value="快照日期"),
            "snapshot_value": tk.StringVar(value="暂无"),
            "snapshot_body": tk.StringVar(value="等待实时快照。"),
            "pnl_title": tk.StringVar(value="组合实时收益"),
            "pnl_value": tk.StringVar(value="暂无"),
            "pnl_body": tk.StringVar(value="等待实时收益快照。"),
            "value_title": tk.StringVar(value="估算仓位市值"),
            "value_value": tk.StringVar(value="暂无"),
            "value_body": tk.StringVar(value="等待估算市值。"),
            "fresh_title": tk.StringVar(value="数据新鲜度"),
            "fresh_value": tk.StringVar(value="暂无"),
            "fresh_body": tk.StringVar(value="等待刷新状态。"),
        }
        self.portfolio_cards = {
            "drift_title": tk.StringVar(value="配置偏离"),
            "drift_value": tk.StringVar(value="暂无"),
            "drift_body": tk.StringVar(value="等待目标配置与当前偏离载入。"),
            "rebalance_title": tk.StringVar(value="再平衡"),
            "rebalance_value": tk.StringVar(value="暂无"),
            "rebalance_body": tk.StringVar(value="等待再平衡建议。"),
            "risk_title": tk.StringVar(value="组合重点"),
            "risk_value": tk.StringVar(value="暂无"),
            "risk_body": tk.StringVar(value="等待组合集中度与风险提示。"),
        }

    def _init_runtime_state(self):
        self.task_cards = {}
        self.task_status = initial_task_status()
        self.trade_constraints = {}
        self.trade_suggestions = []
        self.watchlist_items = []
        self.filtered_watchlist_items = []
        self.fund_items = []
        self.filtered_fund_items = []
        self.agent_items = []
        self.filtered_agent_items = []
        self.realtime_items = []
        self.filtered_realtime_items = []
        self.current_review_batches = []
        self.rt_sort_key = self.ui_state.get("sort", {}).get("realtime_key", "abs_pnl")
        self.rt_sort_desc = bool(self.ui_state.get("sort", {}).get("realtime_desc", True))
        self._panes = {}

    def build(self):
        configure_theme(self.root)
        shell = tk.Frame(self.root, bg=THEME["bg"])
        shell.pack(fill="both", expand=True, padx=SPACING["page_x"], pady=SPACING["page_y"])
        self.build_sidebar(shell)
        self.toast_hub = ToastHub(self.root)
        self.toast_hub.on_history_change = self.update_notification_views

        self.nb = ttk.Notebook(self.content_host, style="Content.TNotebook")
        self.nb.pack(fill="both", expand=True)
        self.tab_dash = tk.Frame(self.nb, bg=THEME["bg"])
        self.tab_portfolio = tk.Frame(self.nb, bg=THEME["bg"])
        self.tab_runtime = tk.Frame(self.nb, bg=THEME["bg"])
        self.tab_rt = tk.Frame(self.nb, bg=THEME["bg"])
        self.tab_research = tk.Frame(self.nb, bg=THEME["bg"])
        self.tab_agents = tk.Frame(self.nb, bg=THEME["bg"])
        self.tab_review = tk.Frame(self.nb, bg=THEME["bg"])
        self.tab_trade = tk.Frame(self.nb, bg=THEME["bg"])
        self.tab_settings = tk.Frame(self.nb, bg=THEME["bg"])
        self.tab_frames = {key: getattr(self, f"tab_{key}") for key in TAB_LABELS}

        build_dashboard_view(self)
        build_portfolio_view(self)
        build_runtime_view(self)
        build_realtime_view(self)
        build_research_view(self)
        build_agents_view(self)
        build_review_view(self)
        build_trade_view(self)
        build_settings_view(self)
        self.sync_tabs()

        self.bind_ui_events()
        self.restore_ui_state()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_sidebar(self, parent):
        self.sidebar = tk.Frame(parent, bg=THEME["panel"], bd=0, highlightbackground=THEME["line"], highlightcolor=THEME["line"], highlightthickness=1, width=186)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.content_host = tk.Frame(parent, bg=THEME["bg"])
        self.content_host.pack(side="left", fill="both", expand=True, padx=(SPACING["gap"], 0))

        top = tk.Frame(self.sidebar, bg=THEME["panel"])
        top.pack(fill="x", padx=12, pady=(12, 10))
        tk.Label(top, text="OKRA", bg=THEME["panel"], fg=THEME["ink"], font=TYPOGRAPHY["display"]).pack(anchor="w")
        tk.Label(top, text="小助手", bg=THEME["panel"], fg=THEME["muted"], font=TYPOGRAPHY["small_strong"]).pack(anchor="w", pady=(2, 0))

        self.sidebar_nav = tk.Frame(self.sidebar, bg=THEME["panel"])
        self.sidebar_nav.pack(fill="both", expand=True, padx=10)
        self.nav_buttons: dict[str, ttk.Button] = {}

        bottom = tk.Frame(self.sidebar, bg=THEME["panel"])
        bottom.pack(fill="x", padx=10, pady=10)

        control_card = tk.Frame(bottom, bg=THEME["surface"], bd=0, highlightbackground=THEME["line"], highlightcolor=THEME["line"], highlightthickness=1, padx=10, pady=10)
        control_card.pack(fill="x")
        tk.Label(control_card, text="查看日期", bg=THEME["surface"], fg=THEME["ink_soft"], font=TYPOGRAPHY["small"]).pack(anchor="w")
        self.date_combo = WheelCombobox(control_card, textvariable=self.date_var, width=12, state="readonly")
        self.date_combo.pack(fill="x", pady=(6, 0))
        ttk.Button(control_card, text="回到今天", command=self.switch_to_today, style="Primary.TButton").pack(fill="x", pady=(8, 0))
        ttk.Button(control_card, text="刷新", command=self.on_refresh, style="Ghost.TButton").pack(fill="x", pady=(6, 0))

        status_card = tk.Frame(bottom, bg=THEME["surface_soft"], bd=0, highlightbackground=THEME["line"], highlightcolor=THEME["line"], highlightthickness=1, padx=10, pady=10)
        status_card.pack(fill="x", pady=(8, 0))
        make_badge(status_card, text_var=self.status_var, tone="info").pack(anchor="w")
        tk.Label(status_card, textvariable=self.hero_context_var, bg=THEME["surface_soft"], fg=THEME["ink_soft"], font=TYPOGRAPHY["small"], wraplength=144, justify="left").pack(anchor="w", pady=(8, 0))

    def bind_ui_events(self):
        self.date_combo.bind("<<ComboboxSelected>>", lambda _e: self.on_date())
        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self.on_tab_changed())

        self.trade_suggestion.bind("<<ComboboxSelected>>", lambda _e: self.apply_trade_suggestion())
        self.trade_fund.bind("<<ComboboxSelected>>", lambda _e: self.refresh_trade_preview())
        self.trade_action_var.trace_add("write", lambda *_args: self.root.after_idle(self.refresh_trade_preview))
        self.trade_amount_var.trace_add("write", lambda *_args: self.root.after_idle(self.refresh_trade_preview))
        self.trade_nav_var.trace_add("write", lambda *_args: self.root.after_idle(self.refresh_trade_preview))
        self.trade_units_var.trace_add("write", lambda *_args: self.root.after_idle(self.refresh_trade_preview))

        self.settings_cap_fund.bind("<<ComboboxSelected>>", lambda _e: self.update_cap_editor())
        self.fund_tree.bind("<<TreeviewSelect>>", lambda _e: self.show_fund_detail())
        self.agent_tree.bind("<<TreeviewSelect>>", lambda _e: self.show_agent_detail())
        self.watchlist_tree.bind("<<TreeviewSelect>>", lambda _e: self.show_watchlist_item())

        for var, callback, key in [
            (self.research_search_var, self.refresh_research, "research_search"),
            (self.research_action_filter_var, self.refresh_research, "research_action"),
            (self.research_status_filter_var, self.refresh_research, "research_status"),
            (self.agent_search_var, self.refresh_agents, "agent_search"),
            (self.agent_status_filter_var, self.refresh_agents, "agent_status"),
            (self.review_source_filter_var, self.refresh_review, "review_source"),
            (self.review_horizon_filter_var, self.refresh_review, "review_horizon"),
            (self.watchlist_search_var, self.refresh_settings, "watchlist_search"),
            (self.watchlist_category_filter_var, self.refresh_settings, "watchlist_category"),
            (self.watchlist_risk_filter_var, self.refresh_settings, "watchlist_risk"),
        ]:
            var.trace_add("write", lambda *_args, v=var, cb=callback, k=key: self._on_filter_change(k, v.get(), cb))

        for name, pane, default_pos in [
            ("runtime", self.runtime_pane, 300),
            ("realtime", self.realtime_pane, 820),
            ("research", self.research_pane, 360),
            ("agents", self.agents_pane, 340),
            ("review", self.review_pane, 420),
            ("trade", self.trade_pane, 620),
            ("settings", self.settings_pane, 720),
        ]:
            self.register_pane(name, pane, default_pos)

    def restore_ui_state(self):
        self.root.after(180, self._restore_last_tab)

    def update_notification_views(self, history: list[dict]):
        lines = []
        for item in history:
            line = f"[{item.get('time', '')}] {item.get('title', '')}"
            if item.get("body"):
                line += f"\n{item['body']}"
            lines.append(line)
        text = "\n\n".join(lines) if lines else "暂无通知。"
        if hasattr(self, "notification_text"):
            self.write(self.notification_text, text)
        if hasattr(self, "dashboard_notice_text"):
            self.write(self.dashboard_notice_text, text)

    def on_close(self):
        self.closing = True
        self.persist_ui_state()
        if self.auto_realtime_job_id is not None:
            try:
                self.root.after_cancel(self.auto_realtime_job_id)
            except Exception:
                pass
            self.auto_realtime_job_id = None
        self.root.destroy()

    def _on_filter_change(self, key: str, value: str, callback):
        self.ui_state.setdefault("filters", {})[key] = value
        self.schedule_ui_state_save()
        self.root.after_idle(callback)

    def current_view_mode(self) -> str:
        return "analyst"

    def _on_view_mode_change(self):
        self.sync_tabs()
        self.root.after_idle(self.refresh)

    def visible_tab_keys(self) -> list[str]:
        mode = self.current_view_mode()
        return TAB_LAYOUTS.get(mode, TAB_LAYOUTS["analyst"])

    def tab_label(self, key: str) -> str:
        mode = self.current_view_mode()
        return TAB_LABELS.get(key, {}).get(mode, TAB_LABELS.get(key, {}).get("analyst", key))

    def current_tab_key(self) -> str | None:
        try:
            selected = self.nb.select()
        except Exception:
            return None
        for key, frame in self.tab_frames.items():
            if str(frame) == selected:
                return key
        return None

    def sync_tabs(self):
        selected_key = self.ui_state.get("last_tab", "dash")
        selected_key = LEGACY_TAB_TO_KEY.get(selected_key, selected_key)
        current_key = self.current_tab_key()
        if current_key:
            selected_key = current_key
        for tab_id in list(self.nb.tabs()):
            self.nb.forget(tab_id)
        for key in self.visible_tab_keys():
            self.nb.add(self.tab_frames[key], text=self.tab_label(key))
        self.refresh_sidebar_nav(selected_key)
        if selected_key not in self.visible_tab_keys():
            selected_key = self.visible_tab_keys()[0]
        self.root.after_idle(lambda key=selected_key: self.select_tab(key))

    def refresh_sidebar_nav(self, selected_key: str | None = None):
        selected = selected_key or self.current_tab_key() or self.ui_state.get("last_tab", "dash")
        visible = self.visible_tab_keys()
        for child in self.sidebar_nav.winfo_children():
            child.destroy()
        self.nav_buttons = {}
        for key in visible:
            glyph = SIDEBAR_TAB_GLYPHS.get(key, "•")
            label = f"{glyph}  {self.tab_label(key)}"
            style = "SideNavActive.TButton" if key == selected else "SideNav.TButton"
            button = ttk.Button(self.sidebar_nav, text=label, command=lambda target=key: self.select_tab(target), style=style)
            button.pack(fill="x", pady=(0, 6))
            self.nav_buttons[key] = button

    def register_pane(self, name: str, pane: tk.PanedWindow, default_pos: int):
        self._panes[name] = pane
        pane.bind("<ButtonRelease-1>", lambda _e, n=name: self.save_pane_position(n))
        self.root.after(120, lambda n=name, d=default_pos: self.restore_pane_position(n, d))

    def restore_pane_position(self, name: str, default_pos: int):
        pane = self._panes.get(name)
        if pane is None:
            return
        pos = int(self.ui_state.get("pane_positions", {}).get(name, default_pos))
        try:
            pane.sash_place(0, pos, 1)
        except Exception:
            pass

    def save_pane_position(self, name: str):
        pane = self._panes.get(name)
        if pane is None:
            return
        try:
            pos = pane.sash_coord(0)[0]
        except Exception:
            return
        self.ui_state.setdefault("pane_positions", {})[name] = pos
        self.schedule_ui_state_save()

    def _restore_last_tab(self):
        target = self.ui_state.get("last_tab", "dash")
        target = LEGACY_TAB_TO_KEY.get(target, target)
        self.select_tab(target)

    def on_tab_changed(self):
        current = self.current_tab_key()
        if not current:
            return
        self.ui_state["last_tab"] = current
        self.refresh_sidebar_nav(current)
        self.schedule_ui_state_save()

    def select_tab(self, title_or_key: str):
        key = LEGACY_TAB_TO_KEY.get(title_or_key, title_or_key)
        if key not in self.visible_tab_keys():
            return
        for tab_id in self.nb.tabs():
            if str(self.tab_frames[key]) == tab_id:
                self.nb.select(tab_id)
                self.refresh_sidebar_nav(key)
                return

    def schedule_ui_state_save(self):
        if self._ui_save_job is not None:
            try:
                self.root.after_cancel(self._ui_save_job)
            except Exception:
                pass
        self._ui_save_job = self.root.after(250, self.persist_ui_state)

    def persist_ui_state(self):
        self._ui_save_job = None
        try:
            save_ui_state(self.home, self.ui_state)
        except Exception:
            pass

    def remember_selection(self, key: str, value: str):
        self.ui_state.setdefault("selections", {})[key] = value
        self.schedule_ui_state_save()

    def open_project_path(self, path: Path):
        open_path(path)

    def write(self, widget, content: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    def append(self, widget, content: str):
        widget.configure(state="normal")
        widget.insert("end", content)
        widget.see("end")
        widget.configure(state="disabled")

    def notify(self, title: str, body: str = "", *, tone: str = "info", action_text: str | None = None, action=None, timeout_ms: int = 5000):
        self.toast_hub.push(title, body, tone=tone, timeout_ms=timeout_ms, action_text=action_text, action=action)

    def env(self):
        return build_runtime_env(self.home)

    def current_live_task_date(self) -> str:
        return today_str()

    def switch_to_today(self):
        self.date_var.set(today_str())
        self.on_refresh()

    def refresh(self):
        self.date_combo["values"] = self.state["dates"]
        self.trade_constraints = build_trade_constraints(self.home, self.state["portfolio"], self.state["selected_date"])
        self.refresh_header_copy()
        self.refresh_shell_context()
        self.refresh_task_cards()
        self.refresh_dash()
        self.refresh_portfolio()
        self.refresh_research()
        self.refresh_agents()
        self.refresh_rt()
        self.refresh_review()
        self.refresh_trade()
        self.refresh_settings()
        self.refresh_auto_realtime_status()

    def on_date(self):
        self.state = load_state(self.home, self.date_var.get())
        self.trade_date_var.set(self.state["selected_date"])
        self.refresh()

    def on_refresh(self):
        self.state = load_state(self.home, self.date_var.get())
        self.date_var.set(self.state["selected_date"])
        self.trade_date_var.set(self.state["selected_date"])
        self.refresh()

    def refresh_shell_context(self):
        self.hero_selected_var.set(f"查看日 {self.state['selected_date']}")
        self.hero_context_var.set(self.today_chain_status_text())

    def refresh_header_copy(self):
        return

    def today_chain_status_text(self) -> str:
        today = today_str()
        manifest = self.state.get("intraday_manifest", {}) or {}
        strategy = self.state.get("strategy", {}) or {}
        report_mode = str(strategy.get("schedule", {}).get("report_mode", "intraday_proxy") or "intraday_proxy").strip()
        report_name = f"{today}.md" if report_mode == "daily_report" else f"{today}_portfolio.md"
        report_exists = (self.home / "reports" / "daily" / report_name).exists()
        validated_exists = (self.home / "db" / "validated_advice" / f"{today}.json").exists()
        status = str(manifest.get("status", "") or "").lower()
        current_step = fix_text(str(manifest.get("current_step", "") or "").strip())
        finished_at = fix_text(str(manifest.get("finished_at", "") or "").strip())
        if status == "running":
            return f"今日链路状态：运行中 | {current_step}" if current_step else "今日链路状态：运行中"
        if status == "ok" or (report_exists and validated_exists):
            return f"今日链路状态：已更新 | {finished_at}" if finished_at else "今日链路状态：已更新"
        if status == "failed":
            errors = manifest.get("errors") or []
            latest_error = fix_text(str(errors[-1].get("error", "")).strip()) if errors else ""
            return f"今日链路状态：运行失败 | {latest_error[:80]}" if latest_error else "今日链路状态：运行失败"
        return "今日链路状态：尚未生成今日研报"

    def _current_exposure_summary(self):
        return self.state.get("llm_context", {}).get("exposure_summary") or analyze_portfolio_exposure(self.state.get("portfolio", {}), self.state.get("strategy", {}))

    def _card_lines(self, items: list[str], empty_text: str, limit: int = 3) -> str:
        if not items:
            return empty_text
        return "\n".join(f"{idx + 1}. {item}" for idx, item in enumerate(items[:limit]))

    def refresh_task_cards(self):
        for task_kind in self.task_cards:
            self.render_task_card(task_kind)
        runtime_parts = [f"{TASK_CARD_SPECS[k]['title']}={self.task_status[k].get('status')}" for k in self.task_status]
        if self.active_job_name:
            runtime_parts.append(f"当前任务={self.active_job_name}")
        self.runtime_banner_var.set(" | ".join(runtime_parts) if runtime_parts else "运行控制台：当前没有任务。")

    def render_task_card(self, task_kind: str):
        runtime = self.task_status[task_kind]
        info = current_task_result_info(self.home, task_kind)
        self.write(self.task_cards[task_kind], build_task_card_text(task_kind, runtime, info))

    def _update_run_clock(self):
        if not self.busy or not self.active_job_started_at:
            return
        elapsed = int((datetime.now() - self.active_job_started_at).total_seconds())
        self.run_hint_var.set(running_hint_text(self.active_job_name, self.active_task_date, elapsed))
        if self.active_task_kind in self.task_status:
            update_task_elapsed(self.task_status, self.active_task_kind, elapsed)
            self.render_task_card(self.active_task_kind)
        self.root.after(1000, self._update_run_clock)

    def _handle_job_line(self, line: str):
        clean = fix_text(line.rstrip())
        if clean:
            self.append(self.run_log_text, clean + "\n")
        step_label = interpret_run_output_line(clean)
        if step_label:
            self.run_step_var.set(step_label)
            if self.active_task_kind in self.task_status:
                update_task_step(self.task_status, self.active_task_kind, step_label)
                self.render_task_card(self.active_task_kind)

    def run_job(self, name, command, done, task_date: str | None = None, task_kind: str | None = None, *, failure_done=None):
        if self.busy:
            self.notify("当前已有任务在运行", "请等待当前任务完成后再触发新的任务。", tone="warning")
            return
        task_date = task_date or self.current_live_task_date()
        self.busy = True
        self.active_job_name = name
        self.active_task_kind = task_kind or ""
        self.active_task_date = task_date
        self.active_job_started_at = datetime.now()
        self.status_var.set(f"{name} 运行中")
        self.run_hint_var.set(running_hint_text(name, task_date, 0))
        self.run_step_var.set("当前步骤：准备启动")
        self.write(self.run_log_text, f"$ {' '.join(command)}\n")
        if task_kind in self.task_status:
            begin_task_status(self.task_status, task_kind, task_date, self.active_job_started_at)
            self.render_task_card(task_kind)
        self._update_run_clock()
        for btn in (self.btn_intra, self.btn_night, self.btn_rt, self.btn_trade, self.btn_preflight):
            btn.configure(state="disabled")

        def safe_after(callback):
            if self.closing:
                return
            try:
                if self.root.winfo_exists():
                    self.root.after(0, callback)
            except Exception:
                pass

        def worker():
            log = desktop_log_path(self.home, name)
            return_code, output = run_streaming_command(command, self.env(), log, lambda raw: safe_after(lambda text=fix_text(raw): self._handle_job_line(text)))
            output = fix_text(output)
            log.write_text(output, encoding="utf-8")

            def finish():
                self.busy = False
                elapsed = int((datetime.now() - self.active_job_started_at).total_seconds()) if self.active_job_started_at else 0
                finished_task_kind = self.active_task_kind
                self.active_job_name = ""
                self.active_task_kind = ""
                self.active_task_date = ""
                self.active_job_started_at = None
                for btn in (self.btn_intra, self.btn_night, self.btn_rt, self.btn_trade, self.btn_preflight):
                    btn.configure(state="normal")
                if finished_task_kind in self.task_status:
                    finish_task_status(self.task_status, finished_task_kind, return_code == 0, datetime.now(), elapsed, str(log))
                    self.render_task_card(finished_task_kind)
                if return_code == 0:
                    self.status_var.set(f"{name} 已完成")
                    self.run_hint_var.set(finished_hint_text(name, task_date, elapsed, True))
                    done(log, output)
                else:
                    self.status_var.set(f"{name} 失败")
                    self.run_hint_var.set(finished_hint_text(name, task_date, elapsed, False))
                    if failure_done is not None:
                        failure_done(log, output)
                    self.notify(f"{name} 失败", f"日志：{log}", tone="danger", action_text="打开日志", action=lambda p=log: self.open_project_path(p))

            safe_after(finish)

        threading.Thread(target=worker, daemon=True).start()

    def run_pipeline(self, mode):
        task_date = self.current_live_task_date()
        cmd = build_pipeline_command(self.home, task_date, mode)
        resume_existing = (mode == "intraday" and should_resume_intraday(self.home, task_date)) or (mode == "nightly" and should_resume_nightly(self.home, task_date))
        if resume_existing:
            cmd.append("--resume-existing")
        self.run_job(
            f"run_{mode}",
            cmd,
            lambda log, _out, run_date=task_date, resumed=resume_existing: (
                self.date_var.set(run_date),
                self.on_refresh(),
                self.notify(
                    f"{mode} 任务已完成",
                    f"运行日期：{run_date}\n{'本次为续跑未完成任务。\n' if resumed else ''}日志：{log}",
                    tone="success",
                    action_text="打开日志",
                    action=lambda p=log: self.open_project_path(p),
                ),
            ),
            task_date=task_date,
            task_kind=mode,
        )

    def run_realtime(self):
        self.run_realtime_job(auto_trigger=False)

    def startup_realtime_refresh(self):
        if self.closing:
            return
        self.run_realtime_job(auto_trigger=True)
        self.schedule_auto_realtime()

    def run_realtime_job(self, auto_trigger: bool):
        task_date = self.current_live_task_date()
        cmd = build_realtime_command(self.home, task_date)
        if auto_trigger and self.busy:
            self.status_var.set("自动实时刷新等待当前任务完成…")
            self.schedule_auto_realtime(delay_ms=AUTO_REALTIME_RETRY_MS)
            self.refresh_auto_realtime_status()
            return
        self.run_job(
            "run_realtime",
            cmd,
            lambda log, _out, run_date=task_date, auto=auto_trigger: (
                self.date_var.set(run_date),
                self.on_refresh(),
                None if auto else self.notify("实时收益快照已刷新", f"运行日期：{run_date}\n日志：{log}", tone="success", action_text="打开日志", action=lambda p=log: self.open_project_path(p)),
            ),
            task_date=task_date,
            task_kind="realtime",
        )

    def schedule_auto_realtime(self, delay_ms: int | None = None):
        if self.auto_realtime_job_id is not None:
            try:
                self.root.after_cancel(self.auto_realtime_job_id)
            except Exception:
                pass
            self.auto_realtime_job_id = None
        actual_delay = delay_ms if delay_ms is not None else AUTO_REALTIME_REFRESH_MS
        self.auto_realtime_next_at = datetime.now() + timedelta(milliseconds=actual_delay)
        self.auto_realtime_job_id = self.root.after(actual_delay, self.auto_realtime_tick)
        self.refresh_auto_realtime_status()

    def auto_realtime_tick(self):
        self.auto_realtime_job_id = None
        self.run_realtime_job(auto_trigger=True)
        self.schedule_auto_realtime()

    def refresh_auto_realtime_status(self):
        rt = self.state.get("realtime", {}) or {}
        last_generated_at = rt.get("generated_at", "")
        self.auto_realtime_var.set(build_auto_realtime_status_text(last_generated_at, self.auto_realtime_next_at, self.busy))

    def run_preflight(self):
        cmd = build_preflight_command(self.home, "desktop")
        self.run_job(
            "run_preflight",
            cmd,
            lambda log, out: (
                self.on_refresh(),
                self.notify("健康检查已完成", f"日志：{log}", tone="success", action_text="打开日志", action=lambda p=log: self.open_project_path(p)),
                hasattr(self, "settings_system_sections") and self.settings_system_sections.render(build_system_schema(self.home, self.state["selected_date"], self.state["portfolio"], self.state.get("project", {}), self.state.get("strategy", {}), self.state.get("watchlist", {}), self.state["llm_config"], self.state["llm_raw"], self.state.get("realtime", {}), self.state.get("preflight", {}), {"intraday": self.state.get("intraday_manifest", {}), "realtime": self.state.get("realtime_manifest", {}), "nightly": self.state.get("nightly_manifest", {})})),
            ),
        )

    def apply_trade_suggestion(self):
        choice = self.trade_suggestion_var.get().strip()
        if not choice:
            return
        suggestion_id = choice.split(" | ", 1)[0]
        item = next((entry for entry in self.trade_suggestions if entry.get("suggestion_id") == suggestion_id), None)
        if not item:
            return
        self.trade_fund_var.set(f"{item.get('fund_code')} | {item.get('fund_name')}")
        action_map = {"add": "buy", "scheduled_dca": "buy", "reduce": "sell", "switch_out": "switch_out"}
        self.trade_action_var.set(action_map.get(item.get("validated_action"), "buy"))
        self.trade_amount_var.set(str(item.get("validated_amount", 0.0)))
        self.refresh_trade_preview()

    def _safe_float(self, value: str) -> float | None:
        try:
            return float(value)
        except Exception:
            return None

    def submit_trade(self):
        choice = self.trade_fund_var.get().strip()
        if not choice:
            self.notify("请先选择基金", "交易录入前需要先绑定基金。", tone="warning")
            return
        amount = self._safe_float(self.trade_amount_var.get().strip())
        if amount is None:
            self.notify("请输入有效金额", "金额字段需要是数字。", tone="warning")
            return
        if amount <= 0:
            self.notify("金额必须大于 0", "请调整交易金额后再提交。", tone="warning")
            return

        extra = []
        for flag, value, label in [("--trade-nav", self.trade_nav_var.get().strip(), "成交净值"), ("--units", self.trade_units_var.get().strip(), "成交份额")]:
            if value:
                if self._safe_float(value) is None:
                    self.notify(f"{label}格式不正确", "请输入数值格式。", tone="warning")
                    return
                extra += [flag, value]

        code, name = choice.split(" | ", 1)
        cmd = build_trade_command(
            self.home,
            self.trade_date_var.get().strip(),
            code,
            name,
            self.trade_action_var.get().strip(),
            f"{amount:.2f}",
            self.trade_note.get("1.0", "end").strip(),
            self.trade_suggestion_var.get().split(" | ", 1)[0] if self.trade_suggestion_var.get().strip() else "",
            extra,
        )
        self.run_job(
            "record_trade",
            cmd,
            lambda log, _out: (
                self.on_refresh(),
                self.notify("交易已记录并回写持仓", f"日志：{log}", tone="success", action_text="打开日志", action=lambda p=log: self.open_project_path(p)),
            ),
        )

    def _display_action(self, action: str) -> str:
        return {"add": "buy", "scheduled_dca": "buy", "reduce": "sell"}.get(action, action or "hold")

    def _restore_tree_selection(self, tree: ttk.Treeview, preferred: str | None):
        if preferred and tree.exists(preferred):
            tree.selection_set(preferred)
            tree.focus(preferred)
            return preferred
        children = tree.get_children()
        if children:
            tree.selection_set(children[0])
            tree.focus(children[0])
            return children[0]
        return None

    def _filter_review_batches(self):
        batches = self.state.get("review_results_for_date", []) or ([self.state["review_result"]] if self.state.get("review_result") else [])
        source_filter = self.review_source_filter_var.get().strip()
        horizon_filter = self.review_horizon_filter_var.get().strip()
        filtered = []
        for item in batches:
            if source_filter not in {"", "全部来源"} and item.get("source", "advice") != source_filter:
                continue
            if horizon_filter not in {"", "全部周期"} and str(int(item.get("horizon", 0))) != horizon_filter:
                continue
            filtered.append(item)
        return filtered

    def refresh_dash(self):
        summary = summarize(self.state)
        validated = self.state["validated"]
        exposure = self._current_exposure_summary()
        previous_date_text = previous_date(self.state["dates"], self.state["selected_date"])
        previous_validated = load_validated_for_date(self.home, previous_date_text)
        alerts = build_dashboard_alerts({**self.state, "home": self.home})
        change_lines = build_action_change_lines(validated, previous_validated, previous_date_text)
        plain_lines = build_plain_language_summary(summary, validated, exposure, alerts)
        tactical_actions = validated.get("tactical_actions", []) or []
        dca_actions = validated.get("dca_actions", []) or []
        hold_actions = validated.get("hold_actions", []) or []
        top_action = tactical_actions[0] if tactical_actions else (dca_actions[0] if dca_actions else {})
        market_view = validated.get("market_view", {}) or {}
        if self.current_view_mode() == "investor":
            self.dash_cards["action_title"].set("今天最重要")
            self.dash_cards["market_title"].set("市场判断")
            self.dash_cards["confidence_title"].set("建议可信度")
            self.dash_cards["risk_title"].set("当前风险")
            self.dash_plan_cards["do_title"].set("现在去做")
            self.dash_plan_cards["wait_title"].set("先观察")
            self.dash_plan_cards["avoid_title"].set("今天别急")
        else:
            self.dash_cards["action_title"].set("今日主动作")
            self.dash_cards["market_title"].set("市场状态")
            self.dash_cards["confidence_title"].set("可信度横幅")
            self.dash_cards["risk_title"].set("风险提醒")
            self.dash_plan_cards["do_title"].set("今天要做")
            self.dash_plan_cards["wait_title"].set("今天可以等")
            self.dash_plan_cards["avoid_title"].set("今天不建议做")
        self.dash_cards["action_value"].set(f"{top_action.get('fund_name', '暂无')}\n{top_action.get('validated_action', 'hold')} {money(top_action.get('validated_amount', 0))}" if top_action else "暂无")
        self.dash_cards["action_body"].set(top_action.get("thesis", "今天没有需要立刻执行的主动动作。") if top_action else "今天没有需要立刻执行的主动动作。")
        self.dash_cards["market_value"].set(market_view.get("regime", "暂无"))
        self.dash_cards["market_body"].set(market_view.get("summary", "等待市场摘要。"))
        self.dash_cards["confidence_value"].set(f"{summary.get('advice_mode', 'unknown')}\n通道 {summary.get('transport_name', '暂无') or '暂无'}")
        self.dash_cards["confidence_body"].set(f"fallback={'是' if summary.get('advice_is_fallback') else '否'} | 失败智能体={len(summary.get('failed_agent_names', []))} | 自检={summary.get('preflight_status', '暂无') or '暂无'}")
        risk_text = alerts[0] if alerts else (f"最大暴露 {exposure.get('largest_theme_family', {}).get('name', '暂无')}" if exposure else "暂无高优先级风险提醒。")
        self.dash_cards["risk_value"].set(risk_text)
        self.dash_cards["risk_body"].set(f"前三主题集中度 {exposure.get('concentration_metrics', {}).get('top3_family_weight_pct', '—')}% | 高波动主题 {exposure.get('concentration_metrics', {}).get('high_volatility_theme_weight_pct', '—')}%" if exposure else "暂无组合暴露数据。")
        self.dashboard_detail.render(build_dashboard_detail_schema(summary, validated, self.state["portfolio"], self.state.get("realtime", {}), exposure, alerts, change_lines, plain_lines, self.state["portfolio_report"], self.current_view_mode()))

    def refresh_portfolio(self):
        exposure = self._current_exposure_summary()
        allocation_plan = exposure.get("allocation_plan", {}) or {}
        concentration = exposure.get("concentration_metrics", {}) or {}
        bucket_summary = exposure.get("by_strategy_bucket", []) or []
        rebalance_text = "需要再平衡" if allocation_plan.get("rebalance_needed") else "暂不再平衡"
        top_bucket = bucket_summary[0]["name"] if bucket_summary else "暂无"
        self.portfolio_meta_var.set(
            f"当前主资金层 {_bucket_label(top_bucket)} | 再平衡状态 {rebalance_text} | 高波动主题 {pct(exposure.get('concentration_metrics', {}).get('high_volatility_theme_weight_pct', 0), 2)}"
        )
        self.portfolio_report_sections.render(build_portfolio_report_schema(self.state, exposure, self.current_view_mode()))

    def refresh_research(self):
        tactical_count = len(self.state["validated"].get("tactical_actions", []) or [])
        dca_count = len(self.state["validated"].get("dca_actions", []) or [])
        hold_count = len(self.state["validated"].get("hold_actions", []) or [])
        committee_ready = bool(self.state.get("aggregate", {}).get("committee_ready"))
        failed_count = len(self.state.get("aggregate", {}).get("failed_agents", []) or [])
        all_items = []
        for section in ("tactical_actions", "dca_actions", "hold_actions"):
            for item in self.state["validated"].get(section, []) or []:
                enriched = dict(item)
                enriched["_section"] = section
                all_items.append(enriched)
        self.fund_items = all_items
        search = self.research_search_var.get().strip().lower()
        action_filter = self.research_action_filter_var.get().strip()
        status_filter = self.research_status_filter_var.get().strip()
        filtered = []
        for item in self.fund_items:
            display_action = self._display_action(item.get("validated_action", "hold"))
            if search and search not in f"{item.get('fund_code', '')} {item.get('fund_name', '')} {item.get('thesis', '')}".lower():
                continue
            if action_filter in {"buy", "sell", "hold", "switch_out"} and display_action != action_filter:
                continue
            if status_filter in {"pending", "partial", "executed"} and item.get("execution_status", "pending") != status_filter:
                continue
            filtered.append(item)
        self.filtered_fund_items = filtered
        committee_text = "ready" if committee_ready else "not_ready"
        self.research_meta_var.set(
            f"filtered {len(filtered)} / total {len(all_items)} | tactical {tactical_count} | dca {dca_count} | hold {hold_count} | committee {committee_text} | failed {failed_count}"
        )
        self.fund_tree.delete(*self.fund_tree.get_children())
        for item in filtered:
            iid = item.get("fund_code", "")
            agent_summary = summarize_fund_agent_signals(self.state.get("aggregate", {}), item.get("fund_code", ""))
            consensus = "conflict" if agent_summary.get("has_conflict") else f"{len(agent_summary.get('supporting_agents', []))}/{len(agent_summary.get('caution_agents', []))}"
            self.fund_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    item.get("fund_code", ""),
                    item.get("fund_name", ""),
                    self._display_action(item.get("validated_action", "hold")),
                    money(item.get("validated_amount", 0)),
                    consensus,
                    item.get("execution_status", "pending"),
                ),
            )
        selected = self._restore_tree_selection(self.fund_tree, self.ui_state.get("selections", {}).get("fund_code"))
        if selected:
            self.show_fund_detail()
        else:
            self.fund_detail_sections.render(None)

    def show_fund_detail(self):
        selection = self.fund_tree.selection()
        if not selection:
            self.fund_detail_sections.render(None)
            return
        code = selection[0]
        item = next((entry for entry in self.filtered_fund_items if entry.get("fund_code") == code), None)
        if not item:
            return
        rt = next((entry for entry in self.realtime_items if entry.get("fund_code") == code), None)
        review_items = [entry for batch in self.current_review_batches for entry in (batch.get("items", []) or [])]
        rv = next((entry for entry in review_items if entry.get("fund_code") == code), None)
        self.fund_detail_sections.render(build_fund_detail_schema(item, rt, rv, self.state.get("aggregate", {}), self.current_view_mode()))
        self.remember_selection("fund_code", code)

    def refresh_agents(self):
        agents = self.state["aggregate"].get("agents", {})
        ordered = self.state["aggregate"].get("ordered_agents", []) or sorted(agents.keys())
        failed_agents = self.state["aggregate"].get("failed_agents", []) or []
        all_items = [(name, agents.get(name, {})) for name in ordered]
        search = self.agent_search_var.get().strip().lower()
        status_filter = self.agent_status_filter_var.get().strip()
        filtered = []
        for name, agent in all_items:
            status = agent.get("status", "unknown")
            normalized = "failed" if status == "failed" else ("degraded" if status == "degraded" else ("success" if status in {"ok", "success"} else status))
            if search and search not in f"{name} {agent.get('output', {}).get('summary', '')}".lower():
                continue
            if status_filter in {"success", "failed", "degraded", "unknown"} and normalized != status_filter:
                continue
            filtered.append((name, agent))
        self.agent_items = all_items
        self.filtered_agent_items = filtered
        stage_counts = self.state.get("aggregate", {}).get("stage_status", {}) or {}
        analyst_ok = stage_counts.get("analyst", {}).get("ok", 0)
        researcher_ok = stage_counts.get("researcher", {}).get("ok", 0)
        manager_ok = stage_counts.get("manager", {}).get("ok", 0)
        self.agents_meta_var.set(
            f"filtered {len(filtered)} / total {len(ordered)} agents | analyst {analyst_ok} | researcher {researcher_ok} | manager {manager_ok} | failed {len(failed_agents)}"
        )
        self.agent_tree.delete(*self.agent_tree.get_children())
        for name, agent in filtered:
            iid = name
            stage_info = build_agent_stage_snapshot(name, self.state.get("aggregate", {}))
            self.agent_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    stage_info.get("label", stage_label(stage_info.get("stage", ""))),
                    name,
                    agent.get("status", "unknown"),
                    num(agent.get("output", {}).get("confidence"), 2),
                ),
            )
        selected = self._restore_tree_selection(self.agent_tree, self.ui_state.get("selections", {}).get("agent_name"))
        if selected:
            self.show_agent_detail()
        else:
            self.agent_detail_sections.render(None)

    def show_agent_detail(self):
        selection = self.agent_tree.selection()
        if not selection:
            self.agent_detail_sections.render(None)
            return
        name = selection[0]
        entry = next((item for item in self.filtered_agent_items if item[0] == name), None)
        if not entry:
            return
        self.agent_detail_sections.render(build_agent_detail_schema(entry[0], entry[1], self.state.get("aggregate", {}), self.current_view_mode()))
        self.remember_selection("agent_name", name)

    def toggle_rt_sort(self, column: str):
        mapping = {"fund": "fund", "role": "role", "pnl": "pnl", "pct": "pct", "divergence": "divergence", "weight": "weight", "anomaly": "anomaly", "conf": "confidence", "mode": "mode", "fresh": "fresh"}
        target = mapping.get(column, "anomaly")
        if self.rt_sort_key == target:
            self.rt_sort_desc = not self.rt_sort_desc
        else:
            self.rt_sort_key = target
            self.rt_sort_desc = target not in {"fund", "role", "mode", "fresh"}
        self.ui_state.setdefault("sort", {})["realtime_key"] = self.rt_sort_key
        self.ui_state.setdefault("sort", {})["realtime_desc"] = self.rt_sort_desc
        display = {"fund": "盈亏绝对值", "role": "盈亏绝对值", "pnl": "今日收益", "pct": "涨跌幅", "confidence": "可信度", "mode": "盈亏绝对值", "fresh": "盈亏绝对值"}.get(self.rt_sort_key, "盈亏绝对值")
        self.rt_sort_var.set(display)
        clean_display = {
            "fund": "基金名称",
            "role": "角色",
            "pnl": "今日收益",
            "pct": "涨跌幅",
            "divergence": "估值-代理分歧",
            "weight": "仓位占比",
            "anomaly": "异常程度",
            "confidence": "可信度",
            "mode": "估算模式",
            "fresh": "数据时效",
        }.get(self.rt_sort_key)
        if clean_display:
            self.rt_sort_var.set(clean_display)
        self.schedule_ui_state_save()
        self.refresh_rt()

    def _sort_realtime_items(self, items: list[dict]):
        combo = self.rt_sort_var.get().strip()
        if combo == "基金名称":
            self.rt_sort_key, self.rt_sort_desc = "fund", False
        elif combo == "角色":
            self.rt_sort_key, self.rt_sort_desc = "role", False
        elif combo == "今日收益":
            self.rt_sort_key, self.rt_sort_desc = "pnl", True
        elif combo == "涨跌幅":
            self.rt_sort_key, self.rt_sort_desc = "pct", True
        elif combo == "估值-代理分歧":
            self.rt_sort_key, self.rt_sort_desc = "divergence", True
        elif combo == "仓位占比":
            self.rt_sort_key, self.rt_sort_desc = "weight", True
        elif combo == "异常程度":
            self.rt_sort_key, self.rt_sort_desc = "anomaly", True
        elif combo == "可信度":
            self.rt_sort_key, self.rt_sort_desc = "confidence", True
        elif combo == "估算模式":
            self.rt_sort_key, self.rt_sort_desc = "mode", False
        elif combo == "数据时效":
            self.rt_sort_key, self.rt_sort_desc = "fresh", True
        if combo == "今日收益":
            self.rt_sort_key, self.rt_sort_desc = "pnl", True
        elif combo == "涨跌幅":
            self.rt_sort_key, self.rt_sort_desc = "pct", True
        elif combo == "可信度":
            self.rt_sort_key, self.rt_sort_desc = "confidence", True
        elif combo == "盈亏绝对值":
            self.rt_sort_key, self.rt_sort_desc = "abs_pnl", True

        def key(item):
            if self.rt_sort_key == "fund":
                return f"{item.get('fund_code', '')} {item.get('fund_name', '')}"
            if self.rt_sort_key == "role":
                return item.get("role", "")
            if self.rt_sort_key == "pnl":
                return float(item.get("estimated_intraday_pnl_amount", 0) or 0)
            if self.rt_sort_key == "pct":
                return float(item.get("effective_change_pct", 0) or 0)
            if self.rt_sort_key == "divergence":
                return float(item.get("divergence_pct", 0) or 0)
            if self.rt_sort_key == "weight":
                return float(item.get("position_weight_pct", 0) or 0)
            if self.rt_sort_key == "anomaly":
                return float(item.get("anomaly_score", 0) or 0)
            if self.rt_sort_key == "confidence":
                return float(item.get("confidence", 0) or 0)
            if self.rt_sort_key == "mode":
                return item.get("mode", "")
            if self.rt_sort_key == "fresh":
                return float(item.get("freshness_age_business_days", 0) or 0)
            return abs(float(item.get("estimated_intraday_pnl_amount", 0) or 0))

        return sorted(items, key=key, reverse=self.rt_sort_desc)

    def _bind_rt_card(self, widget, fund_code: str):
        widget.bind("<Button-1>", lambda _e, code=fund_code: self.select_rt_code(code))
        for child in widget.winfo_children():
            self._bind_rt_card(child, fund_code)

    def _render_realtime_cards(self, items: list[dict]):
        panel = getattr(self, "rt_list_sections", None)
        if panel is None:
            return
        panel.clear()
        if not items:
            create_empty_state(panel.inner, "暂无实时收益", "请先刷新实时收益快照，或等待自动刷新完成。").pack(fill="x")
            return

        container = tk.Frame(panel.inner, bg=panel.token["bg"])
        container.pack(fill="both", expand=True)
        columns = 1
        for index in range(columns):
            container.grid_columnconfigure(index, weight=1)

        selected_code = self.ui_state.get("selections", {}).get("rt_code", "")
        for idx, item in enumerate(items):
            row = idx // columns
            col = idx % columns
            fund_code = item.get("fund_code", "")
            pnl = float(item.get("estimated_intraday_pnl_amount", 0) or 0)
            is_selected = fund_code == selected_code
            if item.get("stale"):
                bg_color, line_color, title_color = THEME["warning_soft"], "#5C4020", THEME["warning"]
            elif pnl < 0:
                bg_color, line_color, title_color = THEME["danger_soft"], "#5C2630", THEME["danger"]
            elif pnl > 0:
                bg_color, line_color, title_color = THEME["success_soft"], "#1D4C3A", THEME["success"]
            else:
                bg_color, line_color, title_color = THEME["surface"], THEME["line"], THEME["ink"]
            if is_selected:
                line_color = THEME["accent"]

            card = tk.Frame(
                container,
                bg=bg_color,
                bd=0,
                highlightbackground=line_color,
                highlightcolor=line_color,
                highlightthickness=2 if is_selected else 1,
                padx=12,
                pady=8,
                cursor="hand2",
            )
            card.grid(row=row, column=col, sticky="ew", padx=0, pady=(0, SPACING["gap_small"]))

            line = tk.Frame(card, bg=bg_color)
            line.pack(fill="x")
            tk.Label(line, text=item.get("fund_name", fund_code), bg=bg_color, fg=title_color, font=TYPOGRAPHY["body_strong"], anchor="w", justify="left", wraplength=230, width=20).pack(side="left")
            tk.Label(line, text=f"{fund_code}", bg=bg_color, fg=THEME["ink_soft"], font=TYPOGRAPHY["small"], width=8, anchor="w").pack(side="left", padx=(8, 0))
            tk.Label(line, text=money(pnl), bg=bg_color, fg=THEME["danger"] if pnl < 0 else THEME["success"] if pnl > 0 else THEME["ink"], font=TYPOGRAPHY["body_strong"], width=12, anchor="e").pack(side="left", padx=(10, 0))
            tk.Label(line, text=pct(item.get("effective_change_pct"), 2), bg=bg_color, fg=THEME["danger"] if pnl < 0 else THEME["success"] if pnl > 0 else THEME["ink"], font=TYPOGRAPHY["body_strong"], width=9, anchor="e").pack(side="left", padx=(10, 0))
            tk.Label(line, text=f"估值 {pct(item.get('estimate_change_pct'), 2)}", bg=bg_color, fg=THEME["ink"], font=TYPOGRAPHY["small"], width=12, anchor="w").pack(side="left", padx=(12, 0))
            tk.Label(line, text=f"代理 {pct(item.get('proxy_change_pct'), 2)}", bg=bg_color, fg=THEME["ink"], font=TYPOGRAPHY["small"], width=12, anchor="w").pack(side="left", padx=(6, 0))
            tk.Label(line, text=f"分歧 {pct(item.get('divergence_pct'), 2)}", bg=bg_color, fg=THEME["ink"], font=TYPOGRAPHY["small"], width=12, anchor="w").pack(side="left", padx=(6, 0))
            tk.Label(line, text=f"异常 {num(item.get('anomaly_score'), 2)}", bg=bg_color, fg=THEME["ink_soft"], font=TYPOGRAPHY["small"], width=10, anchor="w").pack(side="left", padx=(6, 0))
            tk.Label(line, text=f"仓位 {pct(item.get('position_weight_pct'), 2)}", bg=bg_color, fg=THEME["ink_soft"], font=TYPOGRAPHY["small"], width=12, anchor="w").pack(side="left", padx=(6, 0))
            make_badge(line, text=item.get("mode", "unknown"), tone="muted").pack(side="right", padx=(8, 0))
            make_badge(line, text=("陈旧" if item.get("stale") else "同日"), tone="warning" if item.get("stale") else "success").pack(side="right")

            foot = tk.Frame(card, bg=bg_color)
            foot.pack(fill="x", pady=(4, 0))
            tk.Label(
                foot,
                text=f"快照 {item.get('estimate_time', '暂无')} | 行情 {item.get('proxy_time', '暂无')} | 可信度 {num(item.get('confidence'), 2)} | 角色 {item.get('role', '')}",
                bg=bg_color,
                fg=THEME["muted"],
                font=TYPOGRAPHY["small"],
                justify="left",
                wraplength=1000,
            ).pack(anchor="w")

            self._bind_rt_card(card, fund_code)

    def select_rt_code(self, code: str):
        self.remember_selection("rt_code", code)
        self._render_realtime_cards(self.filtered_realtime_items)
        self.show_rt_detail_by_code(code)

    def show_rt_detail_by_code(self, code: str):
        item = next((entry for entry in self.filtered_realtime_items if entry.get("fund_code") == code), None)
        if not item:
            self.rt_detail_sections.render(None)
            return
        self.rt_detail_sections.render(build_realtime_detail_schema(item, self.current_view_mode()))

    def toggle_rt_sort(self, column: str):
        mapping = {
            "fund": "fund",
            "role": "role",
            "pnl": "pnl",
            "pct": "pct",
            "divergence": "divergence",
            "weight": "weight",
            "anomaly": "anomaly",
            "conf": "confidence",
            "mode": "mode",
            "fresh": "fresh",
        }
        display_map = {
            "fund": "基金名称",
            "role": "角色",
            "pnl": "今日收益",
            "pct": "涨跌幅",
            "divergence": "估值-代理分歧",
            "weight": "仓位占比",
            "anomaly": "异常程度",
            "confidence": "可信度",
            "mode": "估算模式",
            "fresh": "数据时效",
        }
        target = mapping.get(column, "anomaly")
        if self.rt_sort_key == target:
            self.rt_sort_desc = not self.rt_sort_desc
        else:
            self.rt_sort_key = target
            self.rt_sort_desc = target not in {"fund", "role", "mode"}
        self.ui_state.setdefault("sort", {})["realtime_key"] = self.rt_sort_key
        self.ui_state.setdefault("sort", {})["realtime_desc"] = self.rt_sort_desc
        self.rt_sort_var.set(display_map.get(self.rt_sort_key, "异常程度"))
        self.schedule_ui_state_save()
        self.refresh_rt()

    def _sort_realtime_items(self, items: list[dict]):
        combo = self.rt_sort_var.get().strip()
        if combo == "基金名称":
            self.rt_sort_key, self.rt_sort_desc = "fund", False
        elif combo == "角色":
            self.rt_sort_key, self.rt_sort_desc = "role", False
        elif combo == "今日收益":
            self.rt_sort_key, self.rt_sort_desc = "pnl", True
        elif combo == "涨跌幅":
            self.rt_sort_key, self.rt_sort_desc = "pct", True
        elif combo == "估值-代理分歧":
            self.rt_sort_key, self.rt_sort_desc = "divergence", True
        elif combo == "仓位占比":
            self.rt_sort_key, self.rt_sort_desc = "weight", True
        elif combo == "异常程度":
            self.rt_sort_key, self.rt_sort_desc = "anomaly", True
        elif combo == "可信度":
            self.rt_sort_key, self.rt_sort_desc = "confidence", True
        elif combo == "估算模式":
            self.rt_sort_key, self.rt_sort_desc = "mode", False
        elif combo == "数据时效":
            self.rt_sort_key, self.rt_sort_desc = "fresh", True
        else:
            self.rt_sort_key, self.rt_sort_desc = "anomaly", True

        def key(item):
            if self.rt_sort_key == "fund":
                return f"{item.get('fund_code', '')} {item.get('fund_name', '')}"
            if self.rt_sort_key == "role":
                return item.get("role", "")
            if self.rt_sort_key == "pnl":
                return float(item.get("estimated_intraday_pnl_amount", 0) or 0)
            if self.rt_sort_key == "pct":
                return float(item.get("effective_change_pct", 0) or 0)
            if self.rt_sort_key == "divergence":
                return float(item.get("divergence_pct", 0) or 0)
            if self.rt_sort_key == "weight":
                return float(item.get("position_weight_pct", 0) or 0)
            if self.rt_sort_key == "anomaly":
                return float(item.get("anomaly_score", 0) or 0)
            if self.rt_sort_key == "confidence":
                return float(item.get("confidence", 0) or 0)
            if self.rt_sort_key == "mode":
                return item.get("mode", "")
            if self.rt_sort_key == "fresh":
                return float(item.get("freshness_age_business_days", 0) or 0)
            return float(item.get("anomaly_score", 0) or 0)

        return sorted(items, key=key, reverse=self.rt_sort_desc)

    def refresh_rt(self):
        rt = self.state.get("realtime", {}) or {}
        rt_date = self.state.get("realtime_date", self.state.get("selected_date", ""))
        if not rt:
            self.rt_cards["snapshot_value"].set("暂无")
            self.rt_cards["snapshot_body"].set("还没有实时收益快照。")
            self.rt_cards["pnl_value"].set("暂无")
            self.rt_cards["pnl_body"].set("请先刷新实时收益快照。")
            self.rt_cards["value_value"].set("暂无")
            self.rt_cards["value_body"].set("等待估算市值。")
            self.rt_cards["fresh_value"].set("暂无")
            self.rt_cards["fresh_body"].set("没有数据时间语义。")
            self.realtime_items = []
            self.filtered_realtime_items = []
            self._render_realtime_cards([])
            self.rt_summary_detail.render({"title": "暂无实时收益快照", "subtitle": "请先点击“刷新实时快照”。"})
            self.rt_detail_sections.render(None)
            return

        totals = rt.get("totals", {}) or {}
        items = list(rt.get("items", []) or [])
        stale_count = sum(1 for item in items if item.get("stale"))
        self.rt_cards["snapshot_title"].set("快照")
        self.rt_cards["pnl_title"].set("实时收益")
        self.rt_cards["value_title"].set("估算市值")
        self.rt_cards["fresh_title"].set("时效")
        self.rt_cards["snapshot_value"].set(rt.get("report_date", rt_date or "暂无"))
        fallback_note = "" if rt_date == self.state.get("selected_date") else f" | 当前查看日无快照，已回退到 {rt_date}"
        self.rt_cards["snapshot_body"].set(f"{rt.get('market_timestamp', '暂无')}{fallback_note}")
        self.rt_cards["pnl_value"].set(money(totals.get("estimated_intraday_pnl_amount", 0)))
        self.rt_cards["pnl_body"].set(f"总盈亏 {money(totals.get('estimated_total_pnl_amount', 0))}")
        self.rt_cards["value_value"].set(money(totals.get("estimated_position_value", 0)))
        self.rt_cards["value_body"].set(f"查看日 {self.state.get('selected_date', '暂无')}")
        self.rt_cards["fresh_value"].set("正常" if stale_count == 0 else f"陈旧 {stale_count} 只")
        self.rt_cards["fresh_body"].set("同日内" if stale_count == 0 else "存在陈旧项")

        self.realtime_items = items
        filtered = self._sort_realtime_items(items)
        self.filtered_realtime_items = filtered
        self._render_realtime_cards(filtered)

        mode_counts: dict[str, int] = {}
        for item in items:
            mode_counts[item.get("mode", "unknown")] = mode_counts.get(item.get("mode", "unknown"), 0) + 1
        anomaly_items = sorted(items, key=lambda entry: float(entry.get("anomaly_score", 0) or 0), reverse=True)[:5]
        self.rt_summary_detail.render(
            {
                "title": "组合实时摘要",
                "subtitle": "默认直接展示全部基金，优先看异常程度最高的项目。",
                "summary_pairs": [
                    ("快照日期", rt.get("report_date", rt_date or "暂无")),
                    ("当前查看日", self.state.get("selected_date", "暂无")),
                    ("实际生成时间", rt.get("generated_at", "暂无")),
                    ("行情时间", rt.get("market_timestamp", "暂无")),
                    ("组合实时收益", money(totals.get("estimated_intraday_pnl_amount", 0))),
                    ("组合估算市值", money(totals.get("estimated_position_value", 0))),
                    ("组合估算总盈亏", money(totals.get("estimated_total_pnl_amount", 0))),
                ],
                "sections": [
                    {"title": "自动刷新状态", "kind": "text", "tone": "soft", "text": self.auto_realtime_var.get()},
                    {"title": "快照说明", "kind": "text", "tone": "panel", "text": ("当前展示的是所选日期的实时快照。" if rt_date == self.state.get("selected_date") else f"当前查看日期 {self.state.get('selected_date')} 暂无实时收益快照，页面已自动回退到最近可用快照 {rt_date}。")},
                    {"title": "模式分布", "kind": "bars", "tone": "panel", "items": [{"label": key, "value": value, "value_text": str(value), "tone": "info"} for key, value in mode_counts.items()]},
                    {"title": "最高异常项", "kind": "bullets", "tone": "warning", "items": [f"{entry.get('fund_name', entry.get('fund_code', '未知'))} | 异常 {num(entry.get('anomaly_score'), 2)} | 分歧 {pct(entry.get('divergence_pct'), 2)} | {money(entry.get('estimated_intraday_pnl_amount', 0))}" for entry in anomaly_items] or ["暂无异常项"]},
                ],
                "raw_text": build_realtime_summary_text(rt),
            }
        )

        selected = self.ui_state.get("selections", {}).get("rt_code")
        if selected and any(item.get("fund_code") == selected for item in filtered):
            self.show_rt_detail_by_code(selected)
        elif filtered:
            self.select_rt_code(filtered[0].get("fund_code", ""))
        else:
            self.rt_detail_sections.render(None)

    def show_rt_detail(self):
        code = self.ui_state.get("selections", {}).get("rt_code", "")
        if not code:
            self.rt_detail_sections.render(None)
            return
        self.show_rt_detail_by_code(code)

    def refresh_review(self):
        memory = self.state["review_memory"]
        metrics = historical_operating_metrics(self.home, 90)
        self.current_review_batches = self._filter_review_batches()
        self.review_meta_var.set(f"筛选后 {len(self.current_review_batches)} 个批次 | lessons {len(memory.get('lessons', []))} 条 | bias adjustments {len(memory.get('bias_adjustments', []))} 条")
        self.review_summary_sections.render(build_review_summary_schema(self.state["selected_date"], self.current_review_batches, memory, metrics, self.state["review_report"]))
        detail_text = self.state["review_report"] or build_review_detail_fallback(self.state["selected_date"], self.current_review_batches)
        self.write(self.review_detail_text, detail_text)

    def refresh_trade(self):
        funds = [f"{fund['fund_code']} | {fund['fund_name']}" for fund in self.state["portfolio"].get("funds", [])]
        self.trade_fund["values"] = funds
        if funds and self.trade_fund_var.get().strip() not in funds:
            preferred = self.ui_state.get("selections", {}).get("trade_fund_code")
            default = next((label for label in funds if preferred and label.startswith(f"{preferred} |")), funds[0])
            self.trade_fund_var.set(default)
        self.trade_suggestions = []
        suggestion_labels = []
        for section in ("tactical_actions", "dca_actions"):
            for item in self.state["validated"].get(section, []) or []:
                if item.get("validated_action") == "hold":
                    continue
                self.trade_suggestions.append(item)
                suggestion_labels.append(f"{item.get('suggestion_id')} | {item.get('fund_name')} | {item.get('validated_action')} {item.get('validated_amount')}")
        self.trade_suggestion["values"] = suggestion_labels
        if suggestion_labels and self.trade_suggestion_var.get().strip() not in suggestion_labels:
            self.trade_suggestion_var.set(suggestion_labels[0])
        items = self.state["trade_journal"].get("items", []) or []
        self.trade_meta_var.set(f"今日建议 {len(self.trade_suggestions)} 条 | 已记录交易 {len(items)} 笔 | 右侧先看检查台，再决定是否提交。")
        self.refresh_trade_preview()
        self.trade_output_sections.render(build_trade_history_schema(self.trade_date_var.get(), items))

    def refresh_trade_preview(self):
        choice = self.trade_fund_var.get().strip()
        if not choice:
            self.trade_precheck_sections.render({"title": "交易前检查台", "subtitle": "请选择基金后再查看检查结果。"})
            return
        code = choice.split(" | ", 1)[0]
        self.remember_selection("trade_fund_code", code)
        selected = next((fund for fund in self.state["portfolio"].get("funds", []) if fund.get("fund_code") == code), None)
        cash = next((fund for fund in self.state["portfolio"].get("funds", []) if fund.get("role") == "cash_hub"), None)
        amount = self._safe_float(self.trade_amount_var.get().strip() or "0") or 0.0
        schema = build_trade_precheck_schema(selected, cash, self.trade_constraints.get(code, {}), self.trade_action_var.get().strip(), amount, self.trade_nav_var.get().strip(), self.trade_units_var.get().strip(), self.current_view_mode())
        self.trade_precheck_sections.render(schema)

    def save_strategy_controls(self):
        try:
            path = update_strategy_controls(
                self.home,
                risk_profile=self.settings_risk_profile_var.get().strip(),
                cash_hub_floor=float(self.settings_cash_floor_var.get().strip()),
                gross_trade_limit=float(self.settings_gross_limit_var.get().strip()),
                net_buy_limit=float(self.settings_net_limit_var.get().strip()),
                dca_amount=float(self.settings_dca_amount_var.get().strip()),
                report_mode=self.settings_report_mode_var.get().strip(),
                core_target_pct=float(self.settings_core_target_var.get().strip()),
                satellite_target_pct=float(self.settings_satellite_target_var.get().strip()),
                tactical_target_pct=float(self.settings_tactical_target_var.get().strip()),
                defense_target_pct=float(self.settings_defense_target_var.get().strip()),
                rebalance_band_pct=float(self.settings_rebalance_band_var.get().strip()),
            )
        except Exception as exc:
            self.notify("保存策略控制失败", str(exc), tone="danger")
            return
        self.on_refresh()
        self.notify("策略控制已保存", str(path), tone="success")

    def update_cap_editor(self):
        selected_cap_code = self.settings_cap_fund_var.get().split(" | ", 1)[0] if self.settings_cap_fund_var.get().strip() else ""
        selected_cap_fund = next((item for item in self.state["portfolio"].get("funds", []) if item.get("fund_code") == selected_cap_code), None)
        self.settings_cap_value_var.set(str(selected_cap_fund.get("cap_value", "")) if selected_cap_fund else "")

    def save_fund_cap(self):
        choice = self.settings_cap_fund_var.get().strip()
        if not choice:
            self.notify("请先选择基金", "需要先选择一只基金再保存上限。", tone="warning")
            return
        code = choice.split(" | ", 1)[0]
        try:
            definition_path, current_path = update_fund_cap_value(self.home, code, float(self.settings_cap_value_var.get().strip()))
        except Exception as exc:
            self.notify("保存单只上限失败", str(exc), tone="danger")
            return
        self.on_refresh()
        self.notify("单只上限已保存", f"{definition_path}\n{current_path}", tone="success")

    def show_watchlist_item(self):
        selection = self.watchlist_tree.selection()
        if not selection:
            return
        code = selection[0]
        item = next((entry for entry in self.filtered_watchlist_items if entry.get("code") == code), None)
        if not item:
            return
        self.watchlist_code_var.set(item.get("code", ""))
        self.watchlist_name_var.set(item.get("name", ""))
        self.watchlist_category_var.set(item.get("category", "active_equity"))
        self.watchlist_benchmark_var.set(item.get("benchmark", ""))
        self.watchlist_risk_var.set(item.get("risk_level", "high"))
        self.remember_selection("watchlist_code", code)

    def save_watchlist_item(self):
        code = self.watchlist_code_var.get().strip()
        name = self.watchlist_name_var.get().strip()
        if not code or not name:
            self.notify("观察池代码和名称不能为空", "请补全代码和名称后再保存。", tone="warning")
            return
        try:
            path = upsert_watchlist_item(
                self.home,
                code=code,
                name=name,
                category=self.watchlist_category_var.get().strip(),
                benchmark=self.watchlist_benchmark_var.get().strip(),
                risk_level=self.watchlist_risk_var.get().strip(),
            )
        except Exception as exc:
            self.notify("保存观察池失败", str(exc), tone="danger")
            return
        self.on_refresh()
        self.notify("观察池已保存", str(path), tone="success")

    def remove_watchlist_item(self):
        selection = self.watchlist_tree.selection()
        if not selection:
            self.notify("请先选择要删除的观察池", "删除前需要先选中左侧条目。", tone="warning")
            return
        code = selection[0]
        if not messagebox.askyesno(APP_TITLE, f"确认删除观察池 {code} 吗？"):
            return
        try:
            path = remove_watchlist_item(self.home, code)
        except Exception as exc:
            self.notify("删除观察池失败", str(exc), tone="danger")
            return
        self.watchlist_code_var.set("")
        self.watchlist_name_var.set("")
        self.watchlist_benchmark_var.set("")
        self.on_refresh()
        self.notify("观察池已删除", str(path), tone="success")

    def refresh_settings(self):
        selected_date = self.state["selected_date"]
        manifests = {"intraday": self.state.get("intraday_manifest", {}), "realtime": self.state.get("realtime_manifest", {}), "nightly": self.state.get("nightly_manifest", {})}
        strategy = self.state.get("strategy", {})
        portfolio_cfg = strategy.get("portfolio", {})
        self.settings_risk_profile_var.set(portfolio_cfg.get("risk_profile", "balanced"))
        self.settings_cash_floor_var.set(str(portfolio_cfg.get("cash_hub_floor", "")))
        self.settings_gross_limit_var.set(str(portfolio_cfg.get("daily_max_gross_trade_amount", portfolio_cfg.get("daily_max_trade_amount", ""))))
        self.settings_net_limit_var.set(str(portfolio_cfg.get("daily_max_net_buy_amount", portfolio_cfg.get("daily_max_trade_amount", ""))))
        self.settings_dca_amount_var.set(str(strategy.get("core_dca", {}).get("amount_per_fund", "")))
        self.settings_report_mode_var.set(strategy.get("schedule", {}).get("report_mode", "intraday_proxy"))
        allocation = strategy.get("allocation", {}) or {}
        targets = allocation.get("targets", {}) or {}
        self.settings_core_target_var.set(str(targets.get("core_long_term", 50.0)))
        self.settings_satellite_target_var.set(str(targets.get("satellite_mid_term", 20.0)))
        self.settings_tactical_target_var.set(str(targets.get("tactical_short_term", 10.0)))
        self.settings_defense_target_var.set(str(targets.get("cash_defense", 20.0)))
        self.settings_rebalance_band_var.set(str(allocation.get("rebalance_band_pct", 5.0)))
        fund_choices = [f"{item.get('fund_code')} | {item.get('fund_name')}" for item in self.state["portfolio"].get("funds", []) if item.get("role") == "tactical"]
        self.settings_cap_fund["values"] = fund_choices
        if fund_choices and self.settings_cap_fund_var.get().strip() not in fund_choices:
            self.settings_cap_fund_var.set(fund_choices[0])
        self.update_cap_editor()

        self.watchlist_items = self.state.get("watchlist", {}).get("funds", []) or []
        search = self.watchlist_search_var.get().strip().lower()
        cat_filter = self.watchlist_category_filter_var.get().strip()
        risk_filter = self.watchlist_risk_filter_var.get().strip()
        filtered = []
        for item in self.watchlist_items:
            if search and search not in f"{item.get('code', '')} {item.get('name', '')}".lower():
                continue
            if cat_filter not in {"", "全部类别"} and item.get("category") != cat_filter:
                continue
            if risk_filter not in {"", "全部风险"} and item.get("risk_level") != risk_filter:
                continue
            filtered.append(item)
        self.filtered_watchlist_items = filtered
        self.watchlist_tree.delete(*self.watchlist_tree.get_children())
        for item in filtered:
            self.watchlist_tree.insert("", "end", iid=item.get("code", ""), values=(item.get("code", ""), item.get("name", ""), item.get("category", ""), item.get("risk_level", "")))
        selected = self._restore_tree_selection(self.watchlist_tree, self.ui_state.get("selections", {}).get("watchlist_code"))
        if selected:
            self.show_watchlist_item()

        preflight_status = self.state.get("preflight", {}).get("status", "暂无")
        self.settings_meta_var.set(f"观察池 {len(filtered)} / {len(self.watchlist_items)} 条 | tactical cap {len(fund_choices)} 只 | 最新自检状态 {preflight_status}")
        self.settings_system_sections.render(
            build_system_schema(
                self.home,
                selected_date,
                self.state["portfolio"],
                self.state.get("project", {}),
                self.state.get("strategy", {}),
                self.state.get("watchlist", {}),
                self.state["llm_config"],
                self.state["llm_raw"],
                self.state.get("realtime", {}),
                self.state.get("preflight", {}),
                manifests,
            )
        )


def main():
    parser = argparse.ArgumentParser(description="Desktop shell for okra assistant.")
    parser.add_argument("--agent-home")
    parser.add_argument("--date")
    parser.add_argument("--dump-state", action="store_true")
    args = parser.parse_args()
    home = Path(args.agent_home).expanduser() if args.agent_home else DEFAULT_AGENT_HOME
    state = load_state(home, args.date)
    if args.dump_state:
        print(json.dumps(summarize(state), ensure_ascii=False, indent=2))
        return
    App(home, args.date).root.mainloop()


if __name__ == "__main__":
    main()
