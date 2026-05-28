import type { PageKey } from "../components/okra/WorkbenchLayout";

export const pageTitles: Record<PageKey, { eyebrow: string; title: string }> = {
  today: { eyebrow: "OKRA", title: "长期记忆投资工作台" },
  portfolio: { eyebrow: "Portfolio", title: "组合与持仓" },
  execution: { eyebrow: "Execution", title: "实际执行同步" },
  research: { eyebrow: "Research", title: "研究建议看板" },
  intelligence: { eyebrow: "Intelligence", title: "资讯与情绪面板" },
  realtime: { eyebrow: "Realtime", title: "实时估值监控" },
  review: { eyebrow: "Memory", title: "长期记忆与复盘" },
  shadowReview: { eyebrow: "Shadow Review", title: "影子决策只读审查" },
  system: { eyebrow: "System", title: "系统运行状态" },
  fundDetail: { eyebrow: "Fund", title: "基金详情" }
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
