import { AlertTriangle, RefreshCcw } from "lucide-react";
import type { ReactNode } from "react";
import { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Navigate, Outlet, Route, Routes, useLocation, useNavigate, useOutletContext, useSearchParams } from "react-router-dom";
import { WorkbenchLayout, type PageKey } from "../components/okra/WorkbenchLayout";
import { Button, Card, EmptyState } from "../components/ui";
import { ApiError, runLongMemoryAction, runTask } from "../lib/api";
import { getTodayAnalysisRuntime, hasTodayAnalysisResult, isTodayAnalysisRunComplete } from "../lib/todayAnalysis";
import {
  useExecutionPageQuery,
  usePortfolioPageQuery,
  useRealtimePageQuery,
  useResearchPageQuery,
  useReviewPageQuery,
  useShellQuery,
  useSystemPageQuery,
  useTodayPageQuery,
  workbenchQueryKeys
} from "../lib/workbenchQuery";

const TodayPage = lazy(async () => ({ default: (await import("./pages/TodayPage")).TodayPage }));
const PortfolioPage = lazy(async () => ({ default: (await import("./pages/PortfolioPage")).PortfolioPage }));
const ExecutionPage = lazy(async () => ({ default: (await import("./pages/ExecutionPage")).ExecutionPage }));
const ResearchPage = lazy(async () => ({ default: (await import("./pages/ResearchPage")).ResearchPage }));
const RealtimePage = lazy(async () => ({ default: (await import("./pages/RealtimePage")).RealtimePage }));
const ReviewPage = lazy(async () => ({ default: (await import("./pages/ReviewPage")).ReviewPage }));
const SystemPage = lazy(async () => ({ default: (await import("./pages/SystemPage")).SystemPage }));
const FundDetailPage = lazy(async () => ({ default: (await import("./pages/FundDetailPage")).FundDetailPage }));

type WorkbenchRouteContext = {
  selectedDate: string;
  refreshAll: () => Promise<void>;
};

const pageTitles: Record<PageKey, { eyebrow: string; title: string }> = {
  today: { eyebrow: "OKRA", title: "长期记忆投资工作台" },
  portfolio: { eyebrow: "Portfolio", title: "组合与持仓" },
  execution: { eyebrow: "Execution", title: "实际执行同步" },
  research: { eyebrow: "Research", title: "研究建议看板" },
  realtime: { eyebrow: "Realtime", title: "实时估值监控" },
  review: { eyebrow: "Memory", title: "长期记忆与复盘" },
  system: { eyebrow: "System", title: "系统运行状态" },
  fundDetail: { eyebrow: "Fund", title: "基金详情" }
};

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/today" replace />} />
      <Route element={<WorkbenchShell />}>
        <Route path="/today" element={<TodayRoute />} />
        <Route path="/portfolio" element={<PortfolioRoute />} />
        <Route path="/execution" element={<ExecutionRoute />} />
        <Route path="/research" element={<ResearchRoute />} />
        <Route path="/realtime" element={<RealtimeRoute />} />
        <Route path="/review" element={<ReviewRoute />} />
        <Route path="/system" element={<SystemRoute />} />
        <Route path="/fund/:fundCode" element={<FundDetailRoute />} />
      </Route>
      <Route path="*" element={<Navigate to="/today" replace />} />
    </Routes>
  );
}

function WorkbenchShell() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [dailyRunning, setDailyRunning] = useState(false);
  const [realtimeRunning, setRealtimeRunning] = useState(false);
  const [error, setError] = useState("");
  const [activeDailyRunId, setActiveDailyRunId] = useState("");
  const queryClient = useQueryClient();
  const requestedDate = searchParams.get("date") ?? "";
  const pageKey = pageKeyFromPath(location.pathname);
  const autoDailyStarted = useRef("");
  const dailyPollRef = useRef<number | null>(null);

  const shellQuery = useShellQuery(requestedDate || undefined);
  const selectedDate = requestedDate || shellQuery.data?.selectedDate || "";
  const dates = useMemo(() => shellQuery.data?.dates ?? (selectedDate ? [selectedDate] : []), [selectedDate, shellQuery.data?.dates]);
  const todayQuery = useTodayPageQuery(selectedDate || undefined, { enabled: Boolean(selectedDate) });

  const refreshAll = async () => {
    await queryClient.invalidateQueries({ queryKey: workbenchQueryKeys.root });
  };

  useEffect(() => {
    if (!shellQuery.data?.selectedDate || requestedDate) return;
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set("date", shellQuery.data!.selectedDate);
        return next;
      },
      { replace: true }
    );
  }, [requestedDate, setSearchParams, shellQuery.data?.selectedDate]);

  useEffect(() => {
    return () => {
      if (dailyPollRef.current !== null) {
        window.clearInterval(dailyPollRef.current);
        dailyPollRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    const data = todayQuery.data;
    if (!data || dailyRunning) return;
    const today = localDateString();
    if (data.selectedDate !== today) return;
    const runtime = getTodayAnalysisRuntime(data.system);
    if (String(runtime?.status ?? "").toLowerCase() === "running" && String(runtime?.runId ?? "")) {
      setDailyRunning(true);
      setActiveDailyRunId(String(runtime?.runId ?? ""));
      void pollDailyResult(String(runtime?.runId ?? ""));
      return;
    }
    if (autoDailyStarted.current === today) return;
    if (hasTodayAnalysisResult(data)) return;
    autoDailyStarted.current = today;
    void triggerDaily(true);
  }, [dailyRunning, todayQuery.data]);

  async function pollDailyResult(runId: string) {
    if (!runId) return;
    if (dailyPollRef.current !== null) {
      window.clearInterval(dailyPollRef.current);
    }
    let attempts = 0;
    const startedAt = Date.now();
    dailyPollRef.current = window.setInterval(() => {
      attempts += 1;
      void todayQuery
        .refetch()
        .then((result) => {
          const data = result.data;
          const runtime = getTodayAnalysisRuntime(data?.system);
          const timedOut = attempts >= 240 || Date.now() - startedAt > 1_200_000;
          if (!data || isTodayAnalysisRunComplete(runtime, runId) || timedOut) {
            if (dailyPollRef.current !== null) {
              window.clearInterval(dailyPollRef.current);
              dailyPollRef.current = null;
            }
            setDailyRunning(false);
            setActiveDailyRunId("");
            void refreshAll();
          }
        })
        .catch((err) => {
          if (dailyPollRef.current !== null) {
            window.clearInterval(dailyPollRef.current);
            dailyPollRef.current = null;
          }
          setDailyRunning(false);
          setActiveDailyRunId("");
          setError(err instanceof Error ? err.message : "刷新今日分析结果失败。");
        });
    }, 5000);
  }

  async function triggerDaily(automatic = false) {
    setError("");
    setDailyRunning(true);
    try {
      const result = await runTask("daily", { force: !automatic });
      const runId = String(result.runId ?? "");
      setActiveDailyRunId(runId);
      await refreshAll();
      if (runId) {
        await pollDailyResult(runId);
      } else {
        setDailyRunning(false);
        setActiveDailyRunId("");
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && err.code === "already_running") {
        const runId = String(err.details?.runId ?? "");
        setError("");
        setDailyRunning(true);
        setActiveDailyRunId(runId);
        await refreshAll();
        if (runId) {
          await pollDailyResult(runId);
          return;
        }
      }
      setDailyRunning(false);
      setActiveDailyRunId("");
      setError(err instanceof Error ? err.message : "今日分析启动失败。");
    }
  }

  async function triggerRealtime() {
    setError("");
    setRealtimeRunning(true);
    try {
      await runTask("realtime");
      window.setTimeout(() => {
        void refreshAll();
        setRealtimeRunning(false);
      }, 900);
    } catch (err) {
      setRealtimeRunning(false);
      setError(err instanceof Error ? err.message : "实时刷新启动失败。");
    }
  }

  const title = pageTitles[pageKey];

  return (
    <WorkbenchLayout
      page={pageKey}
      selectedDate={selectedDate}
      dates={dates}
      onDateChange={(date) => {
        setSearchParams((current) => {
          const next = new URLSearchParams(current);
          next.set("date", date);
          return next;
        });
      }}
      onRunDaily={() => void triggerDaily(false)}
      onRunRealtime={() => void triggerRealtime()}
      system={shellQuery.data?.system}
      systemRunning={dailyRunning || realtimeRunning}
      dailyRunning={dailyRunning}
      fundCode={pageKey === "fundDetail" ? location.pathname.split("/").pop() : undefined}
    >
      {pageKey !== "fundDetail" ? (
        <div className="mb-4 flex items-center justify-between gap-4">
          <div>
            <div className="text-xs font-bold uppercase tracking-normal text-cyan-300">{title.eyebrow}</div>
            <h1 className="mt-1 text-2xl font-black text-slate-50">{title.title}</h1>
          </div>
          <Button variant="secondary" className="gap-2" onClick={() => void refreshAll()} disabled={shellQuery.isFetching}>
            <RefreshCcw className="h-4 w-4" />
            {shellQuery.isFetching ? "刷新中" : "刷新"}
          </Button>
        </div>
      ) : null}
      {error ? (
        <div className="mb-4 flex items-start gap-3 rounded-md border border-rose-500/40 bg-rose-950/30 p-3 text-sm text-rose-100">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>{error}</div>
        </div>
      ) : null}
      {dailyRunning && pageKey !== "fundDetail" ? (
        <div className="mb-4 rounded-md border border-cyan-500/30 bg-cyan-950/25 px-4 py-3 text-sm text-cyan-100">
          正在运行今日分析：同步数据、调用多 Agent 研究、生成当日结论并更新长期记忆。完成后页面会自动刷新。{activeDailyRunId ? ` runId=${activeDailyRunId}` : ""}
        </div>
      ) : null}
      <Outlet context={{ selectedDate, refreshAll } satisfies WorkbenchRouteContext} />
    </WorkbenchLayout>
  );
}

function TodayRoute() {
  const { selectedDate } = useWorkbenchContext();
  const query = useTodayPageQuery(selectedDate || undefined, { enabled: Boolean(selectedDate) });
  return (
    <RouteSuspense>
      <QueryBoundary query={query}>{(data) => <TodayPage snapshot={data} />}</QueryBoundary>
    </RouteSuspense>
  );
}

function PortfolioRoute() {
  const { selectedDate } = useWorkbenchContext();
  const navigate = useNavigate();
  const query = usePortfolioPageQuery(selectedDate || undefined, { enabled: Boolean(selectedDate) });
  return (
    <RouteSuspense>
      <QueryBoundary query={query}>
        {(data) => <PortfolioPage portfolio={data.portfolio} onOpenFundDetail={(code) => navigate(fundHref(code, selectedDate, "portfolio"))} />}
      </QueryBoundary>
    </RouteSuspense>
  );
}

function ExecutionRoute() {
  const { selectedDate, refreshAll } = useWorkbenchContext();
  const query = useExecutionPageQuery(selectedDate || undefined, { enabled: Boolean(selectedDate) });
  return (
    <RouteSuspense>
      <QueryBoundary query={query}>
        {(data) => <ExecutionPage executionSync={data.executionSync} portfolio={data.portfolio} onRefresh={() => void refreshAll()} />}
      </QueryBoundary>
    </RouteSuspense>
  );
}

function ResearchRoute() {
  const { selectedDate } = useWorkbenchContext();
  const navigate = useNavigate();
  const query = useResearchPageQuery(selectedDate || undefined, { enabled: Boolean(selectedDate) });
  return (
    <RouteSuspense>
      <QueryBoundary query={query}>
        {(data) => <ResearchPage research={data.research} onOpenFundDetail={(code) => navigate(fundHref(code, selectedDate, "research"))} />}
      </QueryBoundary>
    </RouteSuspense>
  );
}

function RealtimeRoute() {
  const { selectedDate } = useWorkbenchContext();
  const navigate = useNavigate();
  const query = useRealtimePageQuery(selectedDate || undefined, { enabled: Boolean(selectedDate) });
  return (
    <RouteSuspense>
      <QueryBoundary query={query}>
        {(data) => <RealtimePage realtime={data.realtime} onOpenFundDetail={(code) => navigate(fundHref(code, selectedDate, "realtime"))} />}
      </QueryBoundary>
    </RouteSuspense>
  );
}

function ReviewRoute() {
  const { selectedDate, refreshAll } = useWorkbenchContext();
  const query = useReviewPageQuery(selectedDate || undefined, { enabled: Boolean(selectedDate) });
  const memoryMutation = useMutation({
    mutationFn: ({ memoryId, action, note }: { memoryId: string; action: Parameters<typeof runLongMemoryAction>[1]; note?: string }) =>
      runLongMemoryAction(memoryId, action, note),
    onSuccess: async () => {
      await refreshAll();
    }
  });

  return (
    <RouteSuspense>
      <QueryBoundary query={query}>
        {(data) => (
          <ReviewPage
            review={data.review}
            longMemory={data.longMemory}
            onMemoryAction={async (memoryId, action, note) => {
              await memoryMutation.mutateAsync({ memoryId, action, note });
            }}
          />
        )}
      </QueryBoundary>
    </RouteSuspense>
  );
}

function SystemRoute() {
  const { selectedDate } = useWorkbenchContext();
  const query = useSystemPageQuery(selectedDate || undefined, { enabled: Boolean(selectedDate) });
  return (
    <RouteSuspense>
      <QueryBoundary query={query}>{(data) => <SystemPage system={data.system} summary={data.summary} />}</QueryBoundary>
    </RouteSuspense>
  );
}

function FundDetailRoute() {
  const location = useLocation();
  const navigate = useNavigate();
  const { selectedDate } = useWorkbenchContext();
  const fundCode = location.pathname.split("/").pop() ?? "";
  const from = (new URLSearchParams(location.search).get("from") as PageKey | null) ?? "today";

  if (!fundCode) {
    return <EmptyState title="基金详情缺少基金代码" body="请从持仓、研究或实时页面重新进入基金详情。" />;
  }

  return (
    <RouteSuspense>
      <FundDetailPage fundCode={fundCode} selectedDate={selectedDate} onBack={() => navigate(routeForPage(from, selectedDate))} />
    </RouteSuspense>
  );
}

function QueryBoundary<T>({
  query,
  children
}: {
  query: {
    data: T | undefined;
    isLoading: boolean;
    isError: boolean;
    error: Error | null;
  };
  children: (data: T) => ReactNode;
}) {
  if (query.isLoading && !query.data) {
    return <Card className="flex min-h-[420px] items-center justify-center p-8 text-sm text-slate-300">正在加载页面数据...</Card>;
  }

  if (query.isError || !query.data) {
    return <EmptyState title="页面数据加载失败" body={query.error?.message ?? "暂时没有拿到页面数据。"} />;
  }

  return <>{children(query.data)}</>;
}

function pageKeyFromPath(pathname: string): PageKey {
  if (pathname.startsWith("/portfolio")) return "portfolio";
  if (pathname.startsWith("/execution")) return "execution";
  if (pathname.startsWith("/research")) return "research";
  if (pathname.startsWith("/realtime")) return "realtime";
  if (pathname.startsWith("/review")) return "review";
  if (pathname.startsWith("/system")) return "system";
  if (pathname.startsWith("/fund/")) return "fundDetail";
  return "today";
}

function routeForPage(page: PageKey, selectedDate: string) {
  const path =
    page === "today"
      ? "/today"
      : page === "portfolio"
        ? "/portfolio"
        : page === "execution"
          ? "/execution"
          : page === "research"
            ? "/research"
            : page === "realtime"
              ? "/realtime"
              : page === "review"
                ? "/review"
                : page === "system"
                  ? "/system"
                  : "/today";
  return selectedDate ? `${path}?date=${encodeURIComponent(selectedDate)}` : path;
}

function fundHref(fundCode: string, selectedDate: string, from: Exclude<PageKey, "fundDetail">) {
  const params = new URLSearchParams();
  if (selectedDate) params.set("date", selectedDate);
  params.set("from", from);
  const query = params.toString();
  return `/fund/${encodeURIComponent(fundCode)}${query ? `?${query}` : ""}`;
}

function localDateString() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function useWorkbenchContext() {
  return useOutletContext<WorkbenchRouteContext>();
}

function RouteSuspense({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<Card className="flex min-h-[420px] items-center justify-center p-8 text-sm text-slate-300">正在加载页面模块...</Card>}>
      {children}
    </Suspense>
  );
}
