import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { ResearchDigestBreakdown, ResearchDigestEntry, ResearchPayload, ResearchSentimentBlock, Tone } from "../../lib/types";
import { text } from "../../lib/format";
import { actionLabel } from "../../lib/display";
import { Activity, ArrowRight, Newspaper, RadioTower } from "lucide-react";
import { Badge, Card, EmptyState, MetricCard, SectionTitle } from "../../components/ui";

export function ResearchPage({ research, onOpenFundDetail }: { research: ResearchPayload; onOpenFundDetail?: (fundCode: string) => void }) {
  const [query, setQuery] = useState("");
  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return research.rows;
    return research.rows.filter((row) => JSON.stringify(row).toLowerCase().includes(needle));
  }, [query, research.rows]);

  function fundCodeValue(row: Record<string, unknown>) {
    return text(row.fund_code ?? row.fundCode, "");
  }

  function fundNameValue(row: Record<string, unknown>) {
    return text(row.fund_name ?? row.fundName, fundCodeValue(row));
  }

  function openFundDetail(row: Record<string, unknown>) {
    const code = fundCodeValue(row);
    if (code && onOpenFundDetail) onOpenFundDetail(code);
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-4">
        {research.metrics.map((metric) => (
          <MetricCard key={metric.title} {...metric} />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <SourceHealthPanel sourceHealth={research.source_health} />
        <NewsDigestPanel digest={research.news_digest} eventRisks={research.event_risks} />
        <SentimentDigestPanel digest={research.sentiment_digest} />
      </div>
      <Card className="p-4">
        <div className="mb-4 flex items-center justify-between gap-4">
          <SectionTitle title="基金研究表" meta={research.meta} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索基金、动作、理由"
            className="h-9 w-72 rounded-md border border-slate-800 bg-slate-950 px-3 text-sm text-slate-100 outline-none focus:border-cyan-700"
          />
        </div>
        {rows.length ? (
          <div className="overflow-hidden rounded-md border border-slate-800">
            <table className="w-full border-collapse text-sm">
              <thead className="bg-slate-900 text-xs text-slate-500">
                <tr>
                  <th className="px-3 py-3 text-left">基金</th>
                  <th className="px-3 py-3 text-left">动作</th>
                  <th className="px-3 py-3 text-right">金额</th>
                  <th className="px-3 py-3 text-left">共识</th>
                  <th className="px-3 py-3 text-left">理由</th>
                  <th className="px-3 py-3 text-right">详情</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr
                    key={`${fundCodeValue(row) || "row"}-${index}`}
                    className={`border-t border-slate-800 text-slate-300 ${onOpenFundDetail ? "cursor-pointer hover:bg-slate-900/60" : ""}`}
                    onClick={() => openFundDetail(row)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        openFundDetail(row);
                      }
                    }}
                    role={onOpenFundDetail ? "button" : undefined}
                    tabIndex={onOpenFundDetail ? 0 : undefined}
                  >
                    <td className="px-3 py-3">
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          openFundDetail(row);
                        }}
                        className="w-full text-left"
                      >
                        <div className="font-semibold text-cyan-100 hover:text-cyan-200">{fundNameValue(row)}</div>
                        <div className="text-xs text-slate-500">{fundCodeValue(row)}</div>
                      </button>
                    </td>
                    <td className="px-3 py-3">
                      <Badge tone={text(row.validated_action, "hold") === "hold" ? "neutral" : "accent"}>{actionLabel(row.validated_action)}</Badge>
                    </td>
                    <td className="metric-number px-3 py-3 text-right">{text(row.validated_amount, "0")}</td>
                    <td className="px-3 py-3">
                      <Badge tone={row._has_conflict ? "warning" : "success"}>{text(row._consensus_text, "暂无")}</Badge>
                    </td>
                    <td className="max-w-xl px-3 py-3 text-slate-400">{text(row.thesis || row.reason, "暂无理由")}</td>
                    <td className="px-3 py-3 text-right">
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          openFundDetail(row);
                        }}
                        className="inline-flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-xs font-semibold text-cyan-200 hover:border-cyan-700 hover:bg-slate-900"
                      >
                        查看
                        <ArrowRight className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="暂无研究建议" body="运行今日分析后，这里会显示加仓、定投和观察建议。" />
        )}
      </Card>
    </div>
  );
}

function SourceHealthPanel({ sourceHealth }: { sourceHealth?: ResearchPayload["source_health"] }) {
  const items = Array.isArray(sourceHealth?.items) ? sourceHealth.items : [];
  const warningItems = items.filter((item) => text(item.status, "") !== "ok").slice(0, 3);
  const summary = sourceHealth?.summary ?? {};
  const warningCount = Number(summary.warning_count ?? warningItems.length ?? 0);
  const errorCount = Number(summary.error_count ?? 0);
  const tone: Tone = errorCount > 0 ? "danger" : warningCount > 0 ? "warning" : "success";
  return (
    <InfoPanel
      icon={<Activity className="h-4 w-4" />}
      title="数据源健康"
      badge={<Badge tone={tone}>{errorCount > 0 ? "错误" : warningCount > 0 ? "注意" : "正常"}</Badge>}
      rows={[
        `来源 ${text(summary.source_count, String(items.length))} 个`,
        `warning ${warningCount} / error ${errorCount}`,
        ...warningItems.map((item) => `${text(item.source_key, "source")}: ${text(item.status, "unknown")}`)
      ]}
    />
  );
}

function NewsDigestPanel({ digest, eventRisks }: { digest?: Record<string, unknown>; eventRisks?: Record<string, unknown>[] }) {
  const byRole = asRecord(digest?.by_source_role);
  const risks = Array.isArray(eventRisks) ? eventRisks : [];
  const uniqueCount = text(digest?.unique_item_count, text(digest?.mapped_item_count, text(digest?.item_count, "0")));
  const mappedCount = text(digest?.mapped_item_count, text(digest?.item_count, uniqueCount));
  const duplicateCount = text(digest?.duplicate_item_count, "");
  const sourceBreakdown = summarizeBreakdown(digest?.source_breakdown, ["provider", "source_name", "source_key", "name", "label"]);
  const queryBreakdown = summarizeBreakdown(digest?.query_breakdown, ["query_type", "label", "name", "key"]);
  const topHeatItems = asEntryArray(digest?.top_heat_items);
  const topRiskItems = asEntryArray(digest?.top_risk_items);
  const legacyLatest = asEntryArray(digest?.latest);
  const highlightHeat = topHeatItems[0] ?? legacyLatest[0];
  const highlightRisk = topRiskItems[0] ?? risks[0];
  return (
    <InfoPanel
      icon={<Newspaper className="h-4 w-4" />}
      title="新闻证据"
      badge={<Badge tone={risks.length ? "warning" : "info"}>{uniqueCount} 条</Badge>}
      rows={[
        `唯一 ${uniqueCount} / 映射 ${mappedCount}${duplicateCount ? ` / 重复 ${duplicateCount}` : ""}`,
        sourceBreakdown
          ? `来源分布 ${sourceBreakdown}`
          : `基金 ${text(byRole.fund_news, "0")} / 主题 ${text(byRole.theme_news, "0")} / 市场 ${text(byRole.market_news, "0")}`,
        queryBreakdown ? `查询命中 ${queryBreakdown}` : `事件风险 ${risks.length} 条`,
        highlightHeat
          ? `热点 ${newsHeadline(highlightHeat)}`
          : highlightRisk
            ? `风险 ${newsHeadline(highlightRisk)}`
            : "暂无热点新闻摘要"
      ]}
    />
  );
}

function SentimentDigestPanel({ digest }: { digest?: Record<string, unknown> }) {
  const providers = asEntryArray(digest?.providers);
  const health = asEntryArray(digest?.source_health);
  const warningCount = health.filter((item) => text(item.status, "") !== "ok").length;
  const disabledSources = normalizeDisabledSources(digest?.disabled_sources);
  const classifierHealth = summarizeBreakdown(digest?.classifier_health, ["label", "name", "provider", "key"]);
  const providerHealth = summarizeBreakdown(digest?.provider_health, ["provider", "label", "name", "key"]);
  const textSentiment = asSentimentBlock(digest?.text_sentiment);
  const heatSentiment = asSentimentBlock(digest?.heat_sentiment);
  const derivedSentiment = asSentimentBlock(digest?.derived_sentiment);
  const textScore = text(digest?.text_sentiment_score, text(textSentiment?.score, text(digest?.sentiment_score, "0")));
  const heatScore = text(digest?.heat_score, text(heatSentiment?.score, text(digest?.max_virality_score, "0")));
  const derivedScore = text(digest?.derived_sentiment_score, text(derivedSentiment?.score, "0"));
  const badgeValue = text(digest?.text_sentiment_score, text(digest?.item_count, "0"));
  const badgeLabel = digest?.text_sentiment_score !== undefined ? badgeValue : `${badgeValue} 条`;
  const sentimentSummary = summarizeSentimentBlock(textSentiment);
  const heatSummary = summarizeSentimentBlock(heatSentiment);
  const derivedSummary = summarizeSentimentBlock(derivedSentiment);
  return (
    <InfoPanel
      icon={<RadioTower className="h-4 w-4" />}
      title="新闻与情绪"
      badge={<Badge tone={warningCount ? "warning" : providers.length ? "success" : "neutral"}>{badgeLabel}</Badge>}
      rows={[
        `文本 ${textScore} / 热度 ${heatScore} / 派生 ${derivedScore}`,
        sentimentSummary || heatSummary || derivedSummary
          ? [sentimentSummary, heatSummary, derivedSummary].filter(Boolean).join(" | ")
          : providers.length
            ? `有效来源 ${providers.map((item) => providerName(item)).filter(Boolean).join(", ")}`
            : "暂无情绪摘要",
        classifierHealth
          ? `分类器 ${classifierHealth}`
          : providerHealth
            ? `来源健康 ${providerHealth}`
            : providers.length
              ? `有效来源 ${providers.map((item) => providerName(item)).filter(Boolean).join(", ")}`
              : disabledSources.length
                ? `默认停用 ${disabledSources.join(", ")}`
                : "暂无有效情绪源",
        health.length
          ? `${providerName(health[0])}: ${text(health[0].status, "unknown")}`
          : disabledSources.length
            ? `停用来源 ${disabledSources.join(", ")}`
            : ""
      ]}
    />
  );
}

function InfoPanel({ icon, title, badge, rows }: { icon: ReactNode; title: string; badge: ReactNode; rows: string[] }) {
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="text-cyan-300">{icon}</span>
          <div className="truncate text-sm font-bold text-slate-100">{title}</div>
        </div>
        {badge}
      </div>
      <ul className="space-y-1 text-sm leading-6 text-slate-400">
        {rows.filter(Boolean).slice(0, 4).map((row, index) => (
          <li key={`${title}-${index}`} className="line-clamp-2">
            {row}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asEntryArray(value: unknown): ResearchDigestEntry[] {
  return Array.isArray(value) ? (value as ResearchDigestEntry[]) : [];
}

function asSentimentBlock(value: unknown): ResearchSentimentBlock | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as ResearchSentimentBlock) : undefined;
}

function summarizeBreakdown(value: unknown, labelKeys: string[]): string {
  if (!value) return "";
  if (Array.isArray(value)) {
    return (value as ResearchDigestEntry[])
      .map((entry) => breakdownLabel(entry, labelKeys))
      .filter(Boolean)
      .slice(0, 3)
      .join(" / ");
  }
  const record = asRecord(value as ResearchDigestBreakdown);
  return Object.entries(record)
    .slice(0, 3)
    .map(([key, count]) => `${key} ${text(count, "0")}`)
    .join(" / ");
}

function breakdownLabel(entry: ResearchDigestEntry, labelKeys: string[]): string {
  const label = firstText(entry, labelKeys) || providerName(entry);
  const count = text(entry.count ?? entry.item_count ?? entry.mapped_item_count ?? entry.unique_item_count, "");
  return label && count ? `${label} ${count}` : label;
}

function providerName(entry: ResearchDigestEntry): string {
  return firstText(entry, ["provider", "source_name", "source_key", "name", "label", "key"]);
}

function firstText(entry: ResearchDigestEntry | undefined, keys: string[]): string {
  if (!entry) return "";
  for (const key of keys) {
    const value = text(entry[key], "");
    if (value) return value;
  }
  return "";
}

function newsHeadline(entry: ResearchDigestEntry): string {
  const scope = text(entry.fund_code, "");
  const risk = text(entry.risk_level ?? entry.severity, "");
  const heat = text(entry.heat_score ?? entry.virality_score, "");
  const title = text(entry.title, "暂无标题");
  const tags = [risk, heat ? `热度 ${heat}` : ""].filter(Boolean).join(" / ");
  if (scope && tags) return `${scope}: ${title} (${tags})`;
  if (scope) return `${scope}: ${title}`;
  if (tags) return `${title} (${tags})`;
  return title;
}

function summarizeSentimentBlock(block?: ResearchSentimentBlock): string {
  if (!block) return "";
  const label = text(block.label ?? block.sentiment_label, "");
  const score = text(block.score ?? block.sentiment_score, "");
  const counts = [
    formatCount("正", block.positive_count),
    formatCount("中", block.neutral_count),
    formatCount("负", block.negative_count),
    formatCount("混合", block.mixed_count)
  ]
    .filter(Boolean)
    .join("/");
  const prefix = label || score ? `${label || "摘要"} ${score}`.trim() : "";
  if (prefix && counts) return `${prefix} (${counts})`;
  return prefix || counts;
}

function formatCount(label: string, value: unknown): string {
  const count = text(value, "");
  return count ? `${label}${count}` : "";
}

function normalizeDisabledSources(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") return providerName(item as ResearchDigestEntry);
      return "";
    })
    .filter(Boolean);
}
