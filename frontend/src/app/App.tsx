import { AlertTriangle, RefreshCcw } from "lucide-react";
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { getSnapshot, runLongMemoryAction, runTask } from "../lib/api";
import type { MemoryAction, Snapshot } from "../lib/types";
import { WorkbenchLayout, type PageKey } from "../components/okra/WorkbenchLayout";
import { Button, EmptyState } from "../components/ui";

const FundDetailPage = lazy(() => import("./pages/FundDetailPage").then((module) => ({ default: module.FundDetailPage })));
const PortfolioPage = lazy(() => import("./pages/PortfolioPage").then((module) => ({ default: module.PortfolioPage })));
const RealtimePage = lazy(() => import("./pages/RealtimePage").then((module) => ({ default: module.RealtimePage })));
const ResearchPage = lazy(() => import("./pages/ResearchPage").then((module) => ({ default: module.ResearchPage })));
const ReviewPage = lazy(() => import("./pages/ReviewPage").then((module) => ({ default: module.ReviewPage })));
const SystemPage = lazy(() => import("./pages/SystemPage").then((module) => ({ default: module.SystemPage })));
const TodayPage = lazy(() => import("./pages/TodayPage").then((module) => ({ default: module.TodayPage })));

export function App() {
  const [page, setPage] = useState<PageKey>("today");
  const [previousPage, setPreviousPage] = useState<PageKey>("today");
  const [fundCode, setFundCode] = useState("");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [selectedDate, setSelectedDate] = useState("");
  const [loading, setLoading] = useState(true);
  const [dailyRunning, setDailyRunning] = useState(false);
  const [error, setError] = useState("");
  const dates = useMemo(() => snapshot?.dates ?? (selectedDate ? [selectedDate] : []), [snapshot, selectedDate]);
  const autoDailyStarted = useRef("");

  async function load(date?: string) {
    setLoading(true);
    setError("");
    try {
      const result = await getSnapshot(date);
      setSnapshot(result);
      setSelectedDate(result.selectedDate);
    } catch (err) {
      setError(err instanceof Error ? err.message : "无法连接 OKRA 本地 API。");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (!snapshot || dailyRunning) return;
    const today = localDateString();
    if (snapshot.selectedDate !== today) return;
    if (autoDailyStarted.current === today) return;
    if (hasDailyFirstOpenResult(snapshot)) return;
    autoDailyStarted.current = today;
    void trigger("daily", { automatic: true });
  }, [snapshot, dailyRunning]);

  async function trigger(kind: "daily" | "realtime", options: { force?: boolean; automatic?: boolean } = {}) {
    if (kind === "daily") {
      setDailyRunning(true);
    }
    try {
      await runTask(kind, { force: options.force ?? false });
      if (kind === "daily") {
        pollDailyResult(options.automatic ? "" : selectedDate);
      } else {
        window.setTimeout(() => void load(selectedDate), 900);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "任务启动失败。");
      if (kind === "daily") {
        setDailyRunning(false);
      }
    }
  }

  function pollDailyResult(date: string) {
    let attempts = 0;
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      attempts += 1;
      void getSnapshot(date || undefined)
        .then((result) => {
          setSnapshot(result);
          setSelectedDate(result.selectedDate);
          const timedOut = attempts >= 240 || Date.now() - startedAt > 1_200_000;
          if (hasDailyFirstOpenResult(result) || timedOut) {
            window.clearInterval(timer);
            setDailyRunning(false);
          }
        })
        .catch((err) => {
          window.clearInterval(timer);
          setDailyRunning(false);
          setError(err instanceof Error ? err.message : "刷新首启结果失败。");
        });
    }, 5000);
  }

  async function handleMemoryAction(memoryId: string, action: MemoryAction, note?: string) {
    await runLongMemoryAction(memoryId, action, note);
    await load(selectedDate);
  }

  function openFundDetail(code: string, from: PageKey) {
    setPreviousPage(from);
    setFundCode(code);
    setPage("fundDetail");
  }

  const body = snapshot ? (
    <>
      {page === "today" && <TodayPage snapshot={snapshot} />}
      {page === "portfolio" && <PortfolioPage portfolio={snapshot.portfolio} onOpenFundDetail={(code) => openFundDetail(code, "portfolio")} />}
      {page === "research" && <ResearchPage research={snapshot.research} />}
      {page === "realtime" && <RealtimePage realtime={snapshot.realtime} onOpenFundDetail={(code) => openFundDetail(code, "realtime")} />}
      {page === "review" && <ReviewPage review={snapshot.review} longMemory={snapshot.longMemory} onMemoryAction={handleMemoryAction} />}
      {page === "system" && <SystemPage system={snapshot.system} summary={snapshot.summary} />}
      {page === "fundDetail" && <FundDetailPage fundCode={fundCode} selectedDate={selectedDate} onBack={() => setPage(previousPage)} />}
    </>
  ) : (
    <EmptyState title="等待 OKRA 服务" body="请先启动本地 Python API，或使用桌面快捷方式打开 OKRA 工作台。" />
  );

  return (
    <WorkbenchLayout
      page={page}
      onPageChange={setPage}
      selectedDate={selectedDate}
      dates={dates}
      onDateChange={(date) => {
        setSelectedDate(date);
        void load(date);
      }}
      onRunDaily={() => void trigger("daily", { force: true })}
      onRunRealtime={() => void trigger("realtime")}
      fundCode={page === "fundDetail" ? fundCode : undefined}
    >
      {page !== "fundDetail" ? (
        <div className="mb-4 flex items-center justify-between gap-4">
          <div>
            <div className="text-xs font-bold uppercase tracking-normal text-cyan-300">OKRA</div>
            <h1 className="mt-1 text-2xl font-black text-slate-50">长期记忆投资工作台</h1>
          </div>
          <Button variant="secondary" className="gap-2" onClick={() => void load(selectedDate)} disabled={loading}>
            <RefreshCcw className="h-4 w-4" />
            {loading ? "刷新中" : "刷新"}
          </Button>
        </div>
      ) : null}
      {error ? (
        <div className="mb-4 flex items-start gap-3 rounded-md border border-rose-500/40 bg-rose-950/30 p-3 text-sm text-rose-100">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>{error}</div>
        </div>
      ) : null}
      {dailyRunning ? (
        <div className="mb-4 rounded-md border border-cyan-500/30 bg-cyan-950/25 px-4 py-3 text-sm text-cyan-100">
          正在运行今日首启分析：同步数据、到期复盘、长期记忆更新和今日决策会依次落盘，完成后页面会自动刷新。
        </div>
      ) : null}
      <Suspense fallback={<div className="rounded-md border border-slate-800 bg-slate-950/70 p-4 text-sm text-slate-300">正在加载页面...</div>}>{body}</Suspense>
    </WorkbenchLayout>
  );
}

function hasDailyFirstOpenResult(snapshot: Snapshot) {
  const decision = snapshot.dailyFirstOpen?.decision ?? {};
  const brief = snapshot.dailyFirstOpen?.brief ?? "";
  return Object.keys(decision).length > 0 || brief.trim().length > 0;
}

function localDateString() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
