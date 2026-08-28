"""Compatibility exports for the packaged news query-planning layer."""

from news.query_planner import build_news_query_plan, sentiment_queries_from_plan

__all__ = ["build_news_query_plan", "sentiment_queries_from_plan"]