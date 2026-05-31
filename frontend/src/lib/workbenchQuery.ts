import { useQuery, type UseQueryOptions } from "@tanstack/react-query";
import {
  getExecutionPage,
  getFundDetailPage,
  getIntelligencePage,
  getPortfolioPage,
  getRealtimePage,
  getResearchPage,
  getReviewPage,
  getShadowReviewPage,
  getSystemPage,
  getTodayPage,
  getWorkbenchShell
} from "./workbenchApi";
import type {
  ExecutionPagePayload,
  FundDetailPayload,
  IntelligencePagePayload,
  PortfolioPagePayload,
  RealtimePagePayload,
  ResearchPagePayload,
  ReviewPagePayload,
  ShadowReviewPagePayload,
  ShellPayload,
  SystemPagePayload,
  TodayPagePayload
} from "./types";

export const workbenchQueryKeys = {
  root: ["workbench"] as const,
  shell: (date?: string) => ["workbench", "shell", date ?? "latest"] as const,
  today: (date?: string) => ["workbench", "today", date ?? "latest"] as const,
  portfolio: (date?: string) => ["workbench", "portfolio", date ?? "latest"] as const,
  execution: (date?: string) => ["workbench", "execution", date ?? "latest"] as const,
  research: (date?: string) => ["workbench", "research", date ?? "latest"] as const,
  intelligence: (date?: string) => ["workbench", "intelligence", date ?? "latest"] as const,
  realtime: (date?: string) => ["workbench", "realtime", date ?? "latest"] as const,
  review: (date?: string) => ["workbench", "review", date ?? "latest"] as const,
  shadowReview: (date?: string) => ["workbench", "shadowReview", date ?? "latest"] as const,
  system: (date?: string) => ["workbench", "system", date ?? "latest"] as const,
  fundDetail: (fundCode: string, date?: string, range?: string) => ["workbench", "fundDetail", fundCode, date ?? "latest", range ?? "default"] as const
};

type QueryOverride<T> = Omit<UseQueryOptions<T, Error, T, readonly unknown[]>, "queryKey" | "queryFn">;

export function useShellQuery(date?: string, options?: QueryOverride<ShellPayload>) {
  return useQuery({
    queryKey: workbenchQueryKeys.shell(date),
    queryFn: () => getWorkbenchShell(date),
    staleTime: 30_000,
    ...options
  });
}

export function useTodayPageQuery(date?: string, options?: QueryOverride<TodayPagePayload>) {
  return useQuery({
    queryKey: workbenchQueryKeys.today(date),
    queryFn: () => getTodayPage(date),
    staleTime: 15_000,
    ...options
  });
}

export function usePortfolioPageQuery(date?: string, options?: QueryOverride<PortfolioPagePayload>) {
  return useQuery({
    queryKey: workbenchQueryKeys.portfolio(date),
    queryFn: () => getPortfolioPage(date),
    staleTime: 30_000,
    ...options
  });
}

export function useExecutionPageQuery(date?: string, options?: QueryOverride<ExecutionPagePayload>) {
  return useQuery({
    queryKey: workbenchQueryKeys.execution(date),
    queryFn: () => getExecutionPage(date),
    staleTime: 15_000,
    ...options
  });
}

export function useResearchPageQuery(date?: string, options?: QueryOverride<ResearchPagePayload>) {
  return useQuery({
    queryKey: workbenchQueryKeys.research(date),
    queryFn: () => getResearchPage(date),
    staleTime: 30_000,
    ...options
  });
}

export function useIntelligencePageQuery(date?: string, options?: QueryOverride<IntelligencePagePayload>) {
  return useQuery({
    queryKey: workbenchQueryKeys.intelligence(date),
    queryFn: () => getIntelligencePage(date),
    staleTime: 30_000,
    ...options
  });
}

export function useRealtimePageQuery(date?: string, options?: QueryOverride<RealtimePagePayload>) {
  return useQuery({
    queryKey: workbenchQueryKeys.realtime(date),
    queryFn: () => getRealtimePage(date),
    staleTime: 10_000,
    refetchInterval: 60_000,
    ...options
  });
}

export function useReviewPageQuery(date?: string, options?: QueryOverride<ReviewPagePayload>) {
  return useQuery({
    queryKey: workbenchQueryKeys.review(date),
    queryFn: () => getReviewPage(date),
    staleTime: 30_000,
    ...options
  });
}

export function useShadowReviewPageQuery(date?: string, options?: QueryOverride<ShadowReviewPagePayload>) {
  return useQuery({
    queryKey: workbenchQueryKeys.shadowReview(date),
    queryFn: () => getShadowReviewPage(date),
    staleTime: 30_000,
    ...options
  });
}

export function useSystemPageQuery(date?: string, options?: QueryOverride<SystemPagePayload>) {
  return useQuery({
    queryKey: workbenchQueryKeys.system(date),
    queryFn: () => getSystemPage(date),
    staleTime: 15_000,
    ...options
  });
}

export function useFundDetailQuery(fundCode: string, date?: string, range?: string, options?: QueryOverride<FundDetailPayload>) {
  return useQuery({
    queryKey: workbenchQueryKeys.fundDetail(fundCode, date, range),
    queryFn: () => getFundDetailPage(fundCode, date, range),
    staleTime: 30_000,
    ...options,
    enabled: Boolean(fundCode) && (options?.enabled ?? true)
  });
}
