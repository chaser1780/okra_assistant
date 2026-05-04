from __future__ import annotations

from .dashboard import DashboardPage
from .data_pages import AgentsPage, PortfolioPage, RealtimePage, ResearchPage
from .holding_pages import FundDetailPage, HoldingsTrendPage
from .insights_pages import ReviewPage, SettingsPage
from .runtime_page import RuntimePage
from .trade_page import TradePage


QT_PAGE_FACTORIES = {
    "dash": lambda shell: DashboardPage(shell),
    "portfolio": lambda shell: PortfolioPage(),
    "holdings": lambda shell: HoldingsTrendPage(),
    "research": lambda shell: ResearchPage(shell),
    "trade": lambda shell: TradePage(shell),
    "review": lambda shell: ReviewPage(shell),
    "rt": lambda shell: RealtimePage(shell),
    "agents": lambda shell: AgentsPage(),
    "runtime": lambda shell: RuntimePage(shell),
    "settings": lambda shell: SettingsPage(shell.home, shell),
    "fund_detail": lambda shell: FundDetailPage(),
}


def create_qt_pages(shell) -> dict[str, object]:
    return {key: factory(shell) for key, factory in QT_PAGE_FACTORIES.items()}
