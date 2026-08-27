"""Package-local compatibility entrypoint for the news query planner."""

from news_query_planner import build_news_query_plan, sentiment_queries_from_plan

__all__ = ["build_news_query_plan", "sentiment_queries_from_plan"]
