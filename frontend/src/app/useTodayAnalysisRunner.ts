import { useEffect, useRef, useState } from "react";
import { ApiError, runTask } from "../lib/api";
import { getTodayAnalysisRuntime, hasTodayAnalysisResult, isTodayAnalysisRunComplete } from "../lib/todayAnalysis";
import type { TodayPagePayload } from "../lib/types";

type TodayQueryLike = {
  data: TodayPagePayload | undefined;
  refetch: () => Promise<{ data: TodayPagePayload | undefined }>;
};

type UseTodayAnalysisRunnerArgs = {
  todayQuery: TodayQueryLike;
  refreshAll: () => Promise<void>;
};

export function useTodayAnalysisRunner({ todayQuery, refreshAll }: UseTodayAnalysisRunnerArgs) {
  const [dailyRunning, setDailyRunning] = useState(false);
  const [dailyError, setDailyError] = useState("");
  const [activeDailyRunId, setActiveDailyRunId] = useState("");
  const autoDailyStarted = useRef("");
  const dailyPollRef = useRef<number | null>(null);

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
          setDailyError(err instanceof Error ? err.message : "刷新今日分析结果失败。");
        });
    }, 5000);
  }

  async function triggerDaily(automatic = false) {
    setDailyError("");
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
        setDailyError("");
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
      setDailyError(err instanceof Error ? err.message : "今日分析启动失败。");
    }
  }

  return {
    activeDailyRunId,
    dailyError,
    dailyRunning,
    triggerDaily
  };
}

function localDateString() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
