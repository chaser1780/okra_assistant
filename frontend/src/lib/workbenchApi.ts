import type { z } from "zod";
import { ApiError, getFundDetail, getSnapshot, request } from "./api";
import {
  executionPageSchema,
  fundDetailSchema,
  intelligencePageSchema,
  portfolioPageSchema,
  realtimePageSchema,
  researchPageSchema,
  reviewPageSchema,
  shadowReviewPageSchema,
  shellPayloadSchema,
  systemPageSchema,
  todayPageSchema
} from "./schemas";
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
  Snapshot,
  SystemPagePayload,
  TodayPagePayload
} from "./types";

type Schema<T> = z.ZodType<T>;
const ENABLE_SNAPSHOT_FALLBACK = import.meta.env.VITE_OKRA_ENABLE_SNAPSHOT_FALLBACK === "true";

async function requestWithSchema<T>(path: string, schema: Schema<T>) {
  const payload = await request<unknown>(path);
  return schema.parse(payload);
}

async function withSnapshotFallback<T>(path: string, schema: Schema<T>, fallback: (snapshot: Snapshot) => T, date?: string) {
  try {
    return await requestWithSchema(path, schema);
  } catch (error) {
    if (!ENABLE_SNAPSHOT_FALLBACK || !(error instanceof ApiError) || ![404, 405, 501].includes(error.status)) {
      throw error;
    }
    const snapshot = await getSnapshot(date);
    return fallback(snapshot);
  }
}

function buildDateQuery(date?: string) {
  return date ? `?date=${encodeURIComponent(date)}` : "";
}

export function getWorkbenchShell(date?: string): Promise<ShellPayload> {
  return withSnapshotFallback(`/api/shell${buildDateQuery(date)}`, shellPayloadSchema, (snapshot) => ({
    selectedDate: snapshot.selectedDate,
    dates: snapshot.dates,
    summary: snapshot.summary,
    system: snapshot.system
  }), date);
}

export function getTodayPage(date?: string): Promise<TodayPagePayload> {
  return withSnapshotFallback(`/api/today${buildDateQuery(date)}`, todayPageSchema, (snapshot) => ({
    selectedDate: snapshot.selectedDate,
    dashboard: snapshot.dashboard,
    portfolio: snapshot.portfolio,
    research: snapshot.research,
    longMemory: snapshot.longMemory,
    todayAnalysis: snapshot.todayAnalysis,
    dailyFirstOpen: snapshot.dailyFirstOpen,
    system: snapshot.system
  }), date);
}

export function getPortfolioPage(date?: string): Promise<PortfolioPagePayload> {
  return withSnapshotFallback(`/api/portfolio${buildDateQuery(date)}`, portfolioPageSchema, (snapshot) => ({
    selectedDate: snapshot.selectedDate,
    portfolio: snapshot.portfolio
  }), date);
}

export function getExecutionPage(date?: string): Promise<ExecutionPagePayload> {
  return withSnapshotFallback(`/api/execution${buildDateQuery(date)}`, executionPageSchema, (snapshot) => ({
    selectedDate: snapshot.selectedDate,
    executionSync: snapshot.executionSync,
    portfolio: snapshot.portfolio
  }), date);
}

export function getResearchPage(date?: string): Promise<ResearchPagePayload> {
  return withSnapshotFallback(`/api/research${buildDateQuery(date)}`, researchPageSchema, (snapshot) => ({
    selectedDate: snapshot.selectedDate,
    research: snapshot.research
  }), date);
}

export function getIntelligencePage(date?: string): Promise<IntelligencePagePayload> {
  return withSnapshotFallback(`/api/intelligence${buildDateQuery(date)}`, intelligencePageSchema, (snapshot) => ({
    selectedDate: snapshot.selectedDate,
    intelligence:
      snapshot.intelligence ?? {
        metrics: {},
        source_health: snapshot.research.source_health ?? {},
        news_digest: snapshot.research.news_digest ?? {},
        sentiment_digest: snapshot.research.sentiment_digest ?? {},
        important_news: snapshot.research.news_digest?.top_heat_items ?? [],
        regulatory_items: snapshot.research.event_risks ?? [],
        szse_items: [],
        related_news_by_fund: {},
        source_breakdown: snapshot.research.news_digest?.source_breakdown ?? {},
        event_risks: snapshot.research.event_risks ?? []
      }
  }), date);
}

export function getRealtimePage(date?: string): Promise<RealtimePagePayload> {
  return withSnapshotFallback(`/api/realtime${buildDateQuery(date)}`, realtimePageSchema, (snapshot) => ({
    selectedDate: snapshot.selectedDate,
    realtime: snapshot.realtime
  }), date);
}

export function getReviewPage(date?: string): Promise<ReviewPagePayload> {
  return withSnapshotFallback(`/api/review${buildDateQuery(date)}`, reviewPageSchema, (snapshot) => ({
    selectedDate: snapshot.selectedDate,
    review: snapshot.review,
    longMemory: snapshot.longMemory
  }), date);
}

export function getShadowReviewPage(date?: string): Promise<ShadowReviewPagePayload> {
  return requestWithSchema(`/api/shadow-review${buildDateQuery(date)}`, shadowReviewPageSchema);
}

export function getSystemPage(date?: string): Promise<SystemPagePayload> {
  return withSnapshotFallback(`/api/system${buildDateQuery(date)}`, systemPageSchema, (snapshot) => ({
    selectedDate: snapshot.selectedDate,
    summary: snapshot.summary,
    system: snapshot.system
  }), date);
}

export async function getFundDetailPage(fundCode: string, date?: string, range?: string): Promise<FundDetailPayload> {
  const payload = await getFundDetail(fundCode, date, range);
  return fundDetailSchema.parse(payload);
}
