import { AlertTriangle, RefreshCcw } from "lucide-react";
import type { ReactNode } from "react";
import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Navigate, Outlet, Route, Routes, useLocation, useNavigate, useOutletContext, useSearchParams } from "react-router-dom";
import { WorkbenchLayout, type PageKey } from "../components/okra/WorkbenchLayout";
import { Button, Card, EmptyState } from "../components/ui";
import { runLongMemoryAction, runTask } from "../lib/api";
import {
  useExecutionPageQuery,
  useIntelligencePageQuery,
  usePortfolioPageQuery,
  useRealtimePageQuery,
  useResearchPageQuery,
  useReviewPageQuery,
  useShadowReviewPageQuery,
  useShellQuery,
  useSystemPageQuery,
  useTodayPageQuery,
  workbenchQueryKeys
} from "../lib/workbenchQuery";
import { fundHref, pageKeyFromPath, pageTitles, routeForPage } from "./routeMeta";
import {
  localDateString,
  readAutoRunTodayPreference,
  useTodayAnalysisRunner,
  writeAutoRunTodayPreference
} from "./useTodayAnalysisRunner";

const TodayPage = lazy(async () => ({ default: (await import("./pages/TodayPage")).TodayPage }));
const PortfolioPage = lazy(async () => ({ default: (await import("./pages/PortfolioPage")).PortfolioPage }));
const ExecutionPage = lazy(async () => ({ default: (await import("./pages/ExecutionPage")).ExecutionPage }));
const ResearchPage = lazy(async () => ({ default: (await import("./pages/ResearchPage")).ResearchPage }));
const IntelligencePage = lazy(async () => ({ default: (await import("./pages/IntelligencePage")).IntelligencePage }));
const RealtimePage = lazy(async () => ({ default: (await import("./pages/RealtimePage")).RealtimePage }));
const ReviewPage = lazy(async () => ({ default: (await import("./pages/ReviewPage")).ReviewPage }));
const ShadowReviewPage = lazy(async () => ({ default: (await import("./pages/ShadowReviewPage")).ShadowReviewPage }));
const SystemPage = lazy(async () => ({ default: (await import("./pages/SystemPage")).SystemPage }));
const FundDetailPage = lazy(async () => ({ default: (await import("./pages/FundDetailPage")).FundDetailPage }));

type WorkbenchRouteContext = {
  selectedDate: string;
  refreshAll: () => Promise<void>;
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
        <Route path="/intelligence" element={<IntelligenceRoute />} />
        <Route path="/realtime" element={<RealtimeRoute />} />
        <Route path="/review" element={<ReviewRoute />} />
        <Route path="/shadow-review" element={<ShadowReviewRoute />} />
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
  const [realtimeRunning, setRealtimeRunning] = useState(false);
  const [realtimeError, setRealtimeError] = useState("");
  const realtimeRequestInFlight = useRef(false);
  const [autoRunToday, setAutoRunToday] = useState(readAutoRunTodayPreference);
  const queryClient = useQueryClient();
  const requestedDate = searchParams.get("date") ?? "";
  const pageKey = pageKeyFromPath(location.pathname);

  const shellQuery = useShellQuery(requestedDate || undefined);
  const selectedDate = requestedDate || shellQuery.data?.selectedDate || "";
  const dates = useMemo(() => shellQuery.data?.dates ?? (selectedDate ? [selectedDate] : []), [selectedDate, shellQuery.data?.dates]);
  const todayQuery = useTodayPageQuery(selectedDate || undefined, { enabled: Boolean(selectedDate) });

  const refreshAll = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: workbenchQueryKeys.root });
  }, [queryClient]);
  const { activeDailyRunId, dailyError, dailyRunning, triggerDaily } = useTodayAnalysisRunner({
    autoRunToday,
    todayQuery,
    refreshAll,
    selectedDate
  });
  const error = dailyError || realtimeError;
  const today = localDateString();
  const historicalView = Boolean(selectedDate && selectedDate !== today);

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


  const triggerRealtime = useCallback(async (automatic = false) => {
    if (realtimeRequestInFlight.current) return;
    realtimeRequestInFlight.current = true;
    if (!automatic) setRealtimeError("");
    setRealtimeRunning(true);
    try {
      await runTask("realtime", { date: today });
      await new Promise((resolve) => window.setTimeout(resolve, 4_000));
      await refreshAll();
      setRealtimeError("");
    } catch (err) {
      setRealtimeError(err instanceof Error ? err.message : "实时刷新启动失败。");
    } finally {
      realtimeRequestInFlight.current = false;
      setRealtimeRunning(false);
    }
  }, [refreshAll, today]);

  useEffect(() => {
    if (!shellQuery.isSuccess) return;
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") void triggerRealtime(true);
    };
    const initialTimer = window.setTimeout(refreshWhenVisible, 1_500);
    const intervalTimer = window.setInterval(refreshWhenVisible, 60_000);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.clearTimeout(initialTimer);
      window.clearInterval(intervalTimer);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [shellQuery.isSuccess, triggerRealtime]);

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
      onRunRealtime={() => void triggerRealtime(false)}
      autoRunToday={autoRunToday}
      onAutoRunTodayChange={(enabled) => {
        setAutoRunToday(enabled);
        writeAutoRunTodayPreference(enabled);
      }}
      dailyRunLabel={historicalView ? "重跑所选日" : "运行今日分析"}
      dailyRunTarget={selectedDate || today}
      system={shellQuery.data?.system}
      systemRunning={dailyRunning || realtimeRunning}
      dailyRunning={dailyRunning}
      fundCode={pageKey === "fundDetail" ? location.pathname.split("/").pop() : undefined}
    >
      {pageKey !== "fundDetail" ? (
        <div className="mb-4 flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center sm:gap-4">
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

function IntelligenceRoute() {
  const { selectedDate } = useWorkbenchContext();
  const navigate = useNavigate();
  const query = useIntelligencePageQuery(selectedDate || undefined, { enabled: Boolean(selectedDate) });
  return (
    <RouteSuspense>
      <QueryBoundary query={query}>
        {(data) => <IntelligencePage intelligence={data.intelligence} onOpenFundDetail={(code) => navigate(fundHref(code, selectedDate, "intelligence"))} />}
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

function ShadowReviewRoute() {
  const { selectedDate } = useWorkbenchContext();
  const query = useShadowReviewPageQuery(selectedDate || undefined, { enabled: Boolean(selectedDate) });
  return (
    <RouteSuspense>
      <QueryBoundary query={query}>{(data) => <ShadowReviewPage shadowReview={data} />}</QueryBoundary>
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
