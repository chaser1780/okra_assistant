import type { PageKey } from "../components/okra/WorkbenchLayout";

export const pageTitles: Record<PageKey, { eyebrow: string; title: string }> = {
  today: { eyebrow: "研究终端 / OVERVIEW", title: "组合研究终端" },
  portfolio: { eyebrow: "资产 / ASSETS", title: "组合与持仓" },
  execution: { eyebrow: "资产 / SIMULATION", title: "模拟执行台" },
  research: { eyebrow: "研究 / RESEARCH", title: "研究建议" },
  intelligence: { eyebrow: "研究 / INTELLIGENCE", title: "市场情报" },
  realtime: { eyebrow: "研究 / REALTIME", title: "实时估值" },
  review: { eyebrow: "审计 / MEMORY", title: "策略记忆" },
  shadowReview: { eyebrow: "审计 / EXPERIMENT", title: "策略实验审查" },
  system: { eyebrow: "运行 / RUNTIME", title: "运行中心" },
  fundDetail: { eyebrow: "基金 / FUND DETAIL", title: "基金详情" }
};

export function pageKeyFromPath(pathname: string): PageKey {
  if (pathname.startsWith("/portfolio")) return "portfolio";
  if (pathname.startsWith("/execution")) return "execution";
  if (pathname.startsWith("/research")) return "research";
  if (pathname.startsWith("/intelligence")) return "intelligence";
  if (pathname.startsWith("/realtime")) return "realtime";
  if (pathname.startsWith("/review")) return "review";
  if (pathname.startsWith("/shadow-review")) return "shadowReview";
  if (pathname.startsWith("/system")) return "system";
  if (pathname.startsWith("/fund/")) return "fundDetail";
  return "today";
}

export function routeForPage(page: PageKey, selectedDate: string) {
  const path =
    page === "today"
      ? "/today"
      : page === "portfolio"
        ? "/portfolio"
        : page === "execution"
          ? "/execution"
          : page === "research"
            ? "/research"
            : page === "intelligence"
              ? "/intelligence"
              : page === "realtime"
                ? "/realtime"
                : page === "review"
                  ? "/review"
                  : page === "shadowReview"
                    ? "/shadow-review"
                    : page === "system"
                      ? "/system"
                      : "/today";
  return selectedDate ? `${path}?date=${encodeURIComponent(selectedDate)}` : path;
}

export function fundHref(fundCode: string, selectedDate: string, from: Exclude<PageKey, "fundDetail">) {
  const params = new URLSearchParams();
  if (selectedDate) params.set("date", selectedDate);
  params.set("from", from);
  const query = params.toString();
  return `/fund/${encodeURIComponent(fundCode)}${query ? `?${query}` : ""}`;
}
