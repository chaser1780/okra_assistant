import { Activity, AlertTriangle, Building2, ExternalLink, Flame, Newspaper, RadioTower, X } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { NewsIntelligencePayload, ResearchDigestBreakdown, ResearchDigestEntry, Tone } from "../../lib/types";
import { text } from "../../lib/format";
import { narrativeText, valueLabel } from "../../lib/display";
import { openExternalUrl } from "../../lib/api";
import { Badge, Button, Card, EmptyState, MetricCard, SectionTitle } from "../../components/ui";
import { TerminalPanel } from "../../components/okra/TerminalChrome";

export function IntelligencePage({
  intelligence,
  onOpenFundDetail
}: {
  intelligence: NewsIntelligencePayload;
  onOpenFundDetail?: (fundCode: string) => void;
}) {
  const metrics = (intelligence.metrics ?? {}) as Record<string, unknown>;
  const importantNews = entryArray(intelligence.important_news);
  const regulatoryItems = entryArray(intelligence.regulatory_items);
  const szseItems = entryArray(intelligence.szse_items);
  const eventRisks = entryArray(intelligence.event_risks);
  const relatedByFund = intelligence.related_news_by_fund ?? {};
  const sentiment = (intelligence.sentiment_digest ?? {}) as Record<string, unknown>;
  const sourceHealth = ((intelligence.source_health ?? {}) as Record<string, unknown>) || {};
  const healthItems = entryArray(sourceHealth.items);
  const warningItems = healthItems.filter((item) => text(item.status, "") !== "ok").slice(0, 6);
  const topRelated = Object.entries(relatedByFund).slice(0, 6);
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedNewsId = searchParams.get("news") ?? "";
  const selectedNews = collectNewsItems([importantNews, eventRisks, regulatoryItems, szseItems, ...Object.values(relatedByFund)]).find((item) => newsId(item) === selectedNewsId);
  const [drawerItem, setDrawerItem] = useState<ResearchDigestEntry | null>(selectedNews ?? null);

  useEffect(() => {
    setDrawerItem(selectedNews ?? null);
  }, [selectedNewsId, selectedNews]);

  function openNews(item: ResearchDigestEntry) {
    const id = newsId(item);
    setDrawerItem(item);
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (id) next.set("news", id);
        return next;
      },
      { replace: false }
    );
  }

  function closeNews() {
    setDrawerItem(null);
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.delete("news");
        return next;
      },
      { replace: true }
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <MetricCard title="唯一新闻" value={text(metrics.unique_news_count, "0")} body={`映射 ${text(metrics.mapped_news_count, "0")} 条证据`} tone="accent" />
        <MetricCard title="重要新闻" value={text(metrics.important_news_count, String(importantNews.length))} body="高热度、政策或风险事件" tone="warning" />
        <MetricCard title="监管信息" value={text(metrics.regulatory_count, String(regulatoryItems.length))} body={`深交所 ${text(metrics.szse_count, String(szseItems.length))} 条`} tone="info" />
        <MetricCard title="文本情绪" value={scoreText(metrics.text_sentiment_score)} body={`热度 ${scoreText(metrics.heat_score)} / 派生 ${scoreText(metrics.derived_sentiment_score)}`} tone={sentimentTone(metrics.text_sentiment_score)} />
        <MetricCard title="来源健康" value={text(metrics.source_count, String(healthItems.length))} body={`需关注 ${text(metrics.warning_source_count, String(warningItems.length))} 个来源`} tone={warningItems.length ? "warning" : "success"} />
      </div>
      <IntelligenceTimeline importantNews={importantNews} eventRisks={eventRisks} sentiment={sentiment} />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <DigestPanel title="来源分布" icon={<Newspaper className="h-4 w-4" />} rows={breakdownRows(intelligence.source_breakdown)} empty="暂无来源统计" />
        <SentimentPanel sentiment={sentiment} />
        <HealthPanel items={healthItems} warnings={warningItems} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <NewsList title="重要新闻" icon={<Flame className="h-4 w-4" />} items={importantNews} empty="暂无重要新闻，等待新闻抓取或上下文构建。" onOpenNews={openNews} />
        <NewsList title="风险事件" icon={<AlertTriangle className="h-4 w-4" />} items={eventRisks} empty="暂无高优先级风险事件。" onOpenNews={openNews} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <NewsList title="监管与公告" icon={<Building2 className="h-4 w-4" />} items={regulatoryItems} empty="暂无监管公告。运行新闻抓取后会显示 SSE、AMAC、SZSE 等官方来源。" onOpenNews={openNews} />
        <NewsList title="SZSE 深交所" icon={<Building2 className="h-4 w-4" />} items={szseItems} empty="暂无 SZSE 命中。若官方页面为动态加载，会在来源健康中显示抓取状态。" onOpenNews={openNews} />
      </div>

      <Card className="p-4">
        <SectionTitle title="按基金相关新闻" meta={`${topRelated.length} 个基金分组`} />
        {topRelated.length ? (
          <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
            {topRelated.map(([fundCode, items]) => (
              <div key={fundCode} className="rounded-md border border-slate-800 bg-slate-950/40 p-3">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <button type="button" onClick={() => onOpenFundDetail?.(fundCode)} className="text-sm font-bold text-cyan-100 hover:text-cyan-200">
                    {fundCode}
                  </button>
                  <Badge tone="info">{items.length} 条</Badge>
                </div>
                <div className="space-y-2">
                  {items.slice(0, 4).map((item, index) => (
                    <NewsLine key={`${fundCode}-${newsId(item) || index}`} item={item} compact onOpen={openNews} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="暂无按基金映射的新闻" body="RSS、主题新闻或基金公告命中后，这里会按基金代码聚合相关新闻。" />
        )}
      </Card>
      <NewsDetailDrawer item={drawerItem} onClose={closeNews} onOpenFundDetail={onOpenFundDetail} />
    </div>
  );
}

function IntelligenceTimeline({ importantNews, eventRisks, sentiment }: { importantNews: ResearchDigestEntry[]; eventRisks: ResearchDigestEntry[]; sentiment: Record<string, unknown> }) {
  const items = [...importantNews.slice(0, 3), ...eventRisks.slice(0, 2)].sort((a, b) => String(b.published_at ?? "").localeCompare(String(a.published_at ?? "")));
  const score = Number(sentiment.text_sentiment_score ?? sentiment.sentiment_score ?? 0);
  const direction = score > 0.15 ? "偏正" : score < -0.15 ? "偏负" : "中性";
  return (
    <TerminalPanel title="市场事件流" meta={`${items.length} 条重点事件`} className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_260px]">
      <div className="space-y-1">{items.length ? items.map((item, index) => <div key={`${newsId(item)}-${index}`} className="flex items-start gap-3 border-b border-slate-800/70 py-2 last:border-b-0"><span className="mt-1 h-2 w-2 rounded-full bg-cyan-300 shadow-[0_0_8px_rgba(103,232,249,0.6)]" /><div className="min-w-0 flex-1"><div className="line-clamp-1 text-xs font-semibold text-slate-200">{narrativeText(item.title, "暂无标题")}</div><div className="mt-1 text-[10px] text-slate-600">{item.published_at ?? "暂无时间"} · {sourceLabel(providerName(item))}</div></div><Badge tone={item.risk_level === "high" || item.severity === "high" ? "danger" : "warning"}>重点</Badge></div>) : <EmptyState title="暂无事件流" body="抓取新闻后会在这里展示重点市场事件。" />}</div>
      <div className="border-l border-slate-800 pl-4"><div className="text-xs uppercase tracking-[0.14em] text-slate-500">情绪温度</div><div className={`mt-3 text-3xl font-semibold ${score < -0.15 ? "text-rose-300" : score > 0.15 ? "text-emerald-300" : "text-cyan-200"}`}>{direction}</div><div className="mt-2 tabular-nums text-sm text-slate-300">{score.toFixed(2)}</div><div className="mt-4 h-2 bg-slate-900"><div className={`h-full ${score < -0.15 ? "bg-rose-400" : score > 0.15 ? "bg-emerald-400" : "bg-cyan-300"}`} style={{ width: `${Math.min(100, Math.max(4, Math.abs(score) * 100))}%` }} /></div><div className="mt-2 text-[10px] text-slate-600">样本 {text(sentiment.item_count, "0")} 条</div></div>
    </TerminalPanel>
  );
}

function DigestPanel({ title, icon, rows, empty }: { title: string; icon: ReactNode; rows: string[]; empty: string }) {
  return (
    <Card className="p-4">
      <PanelTitle icon={icon} title={title} />
      {rows.length ? (
        <div className="mt-3 space-y-2">
          {rows.slice(0, 6).map((row) => (
            <div key={row} className="flex items-center justify-between gap-3 text-sm">
              <span className="truncate text-slate-300">{sourceLabel(row.split(" ").slice(0, -1).join(" "))}</span>
              <Badge tone="neutral">{row.split(" ").slice(-1)[0]}</Badge>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-3 text-sm text-slate-500">{empty}</div>
      )}
    </Card>
  );
}

function SentimentPanel({ sentiment }: { sentiment: Record<string, unknown> }) {
  const textBlock = asRecord(sentiment.text_sentiment);
  const heatBlock = asRecord(sentiment.heat_sentiment);
  const derivedBlock = asRecord(sentiment.derived_sentiment);
  return (
    <Card className="p-4">
      <PanelTitle icon={<RadioTower className="h-4 w-4" />} title="情绪摘要" />
      <div className="mt-3 grid grid-cols-3 gap-2">
        <MiniStat label="文本" value={scoreText(sentiment.text_sentiment_score ?? textBlock.score ?? sentiment.sentiment_score)} tone={sentimentTone(sentiment.text_sentiment_score ?? textBlock.score)} />
        <MiniStat label="热度" value={scoreText(sentiment.heat_score ?? heatBlock.score)} tone="warning" />
        <MiniStat label="派生" value={scoreText(sentiment.derived_sentiment_score ?? derivedBlock.score)} tone="info" />
      </div>
      <div className="mt-3 space-y-1 text-sm text-slate-400">
        <div>正面 {text(textBlock.positive_count, "0")} / 中性 {text(textBlock.neutral_count ?? textBlock.mixed_count, "0")} / 负面 {text(textBlock.negative_count, "0")}</div>
        <div>有效来源 {text(sentiment.provider_count, "0")} / 文本池 {text(sentiment.item_count, "0")} 条</div>
        <div>最高传播 {scoreText(sentiment.max_virality_score)}</div>
      </div>
    </Card>
  );
}

function HealthPanel({ items, warnings }: { items: ResearchDigestEntry[]; warnings: ResearchDigestEntry[] }) {
  const rows = (warnings.length ? warnings : items).slice(0, 6);
  return (
    <Card className="p-4">
      <PanelTitle icon={<Activity className="h-4 w-4" />} title="RSS 与来源健康" />
      {rows.length ? (
        <div className="mt-3 space-y-2">
          {rows.map((item, index) => (
            <div key={`${text(item.source_key, "source")}-${index}`} className="flex items-start justify-between gap-3 text-sm">
              <div className="min-w-0">
                <div className="truncate font-semibold text-slate-300">{sourceLabel(providerName(item))}</div>
                <div className="truncate text-xs text-slate-500">{narrativeText(notes(item), "暂无备注")}</div>
              </div>
              <Badge tone={text(item.status, "") === "ok" ? "success" : "warning"}>{valueLabel(item.status)}</Badge>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-3 text-sm text-slate-500">暂无来源健康信息。</div>
      )}
    </Card>
  );
}

function NewsList({ title, icon, items, empty, onOpenNews }: { title: string; icon: ReactNode; items: ResearchDigestEntry[]; empty: string; onOpenNews: (item: ResearchDigestEntry) => void }) {
  return (
    <Card className="p-4">
      <PanelTitle icon={icon} title={title} badge={<Badge tone={items.length ? "info" : "neutral"}>{items.length} 条</Badge>} />
      {items.length ? (
        <div className="mt-3 space-y-3">
          {items.slice(0, 8).map((item, index) => (
            <NewsLine key={`${newsId(item) || text(item.title, "news")}-${index}`} item={item} onOpen={onOpenNews} />
          ))}
        </div>
      ) : (
        <div className="mt-3 text-sm text-slate-500">{empty}</div>
      )}
    </Card>
  );
}

function NewsLine({ item, compact = false, onOpen }: { item: ResearchDigestEntry; compact?: boolean; onOpen: (item: ResearchDigestEntry) => void }) {
  const title = narrativeText(item.title, "暂无标题");
  const risk = text(item.risk_level ?? item.severity, "");
  return (
    <button type="button" onClick={() => onOpen(item)} className="block w-full rounded-md border border-slate-800 bg-slate-950/40 p-3 text-left transition hover:border-cyan-700/70 hover:bg-slate-900/70 focus:outline-none focus:ring-2 focus:ring-cyan-500/40">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="line-clamp-2 text-sm font-semibold text-slate-100">{title}</div>
          {!compact ? <div className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{narrativeText(item.summary, "暂无摘要")}</div> : null}
        </div>
        <Badge tone={risk === "high" ? "danger" : risk === "medium" ? "warning" : "neutral"}>{valueLabel(risk || item.source_role || "news")}</Badge>
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
        <span>{text(item.published_at, "暂无时间")}</span>
        <span>{sourceLabel(providerName(item))}</span>
        {text(item.heat_score, "") ? <span>热度 {scoreText(item.heat_score)}</span> : null}
      </div>
    </button>
  );
}

function NewsDetailDrawer({
  item,
  onClose,
  onOpenFundDetail
}: {
  item: ResearchDigestEntry | null;
  onClose: () => void;
  onOpenFundDetail?: (fundCode: string) => void;
}) {
  const [openingUrl, setOpeningUrl] = useState(false);
  const [openError, setOpenError] = useState("");
  if (!item) return null;
  const title = narrativeText(item.title, "暂无标题");
  const sourceUrl = text(item.canonical_url ?? item.source_url ?? item.url ?? item.evidence_url, "");
  const canOpenSource = isHttpUrl(sourceUrl);
  const fundCode = text(item.code ?? item.fund_code, "");
  const risk = text(item.risk_level ?? item.severity, "");

  async function handleOpenSource() {
    if (!sourceUrl) return;
    setOpenError("");
    if (!canOpenSource) {
      setOpenError("当前原文链接不是有效的 http/https 地址。");
      return;
    }
    setOpeningUrl(true);
    try {
      await openExternalUrl(sourceUrl);
    } catch (error) {
      const fallback = window.open(sourceUrl, "_blank", "noopener,noreferrer");
      if (!fallback) {
        setOpenError(error instanceof Error ? error.message : "打开原文失败，请复制链接到浏览器。");
      }
    } finally {
      setOpeningUrl(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/55 backdrop-blur-sm">
      <button type="button" aria-label="关闭资讯详情" className="absolute inset-0 cursor-default" onClick={onClose} />
      <aside className="relative ml-auto flex h-full w-full max-w-[540px] flex-col border-l border-slate-800 bg-[#080d16] shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-800 px-5 py-4">
          <div className="min-w-0">
            <div className="text-xs font-bold uppercase tracking-[0.16em] text-cyan-300">资讯详情 / NEWS</div>
            <h2 className="mt-1 line-clamp-2 text-base font-bold text-slate-50">{title}</h2>
          </div>
          <Button variant="ghost" className="h-8 shrink-0 gap-2 px-2" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          <div className="mb-4 flex flex-wrap gap-2">
            <Badge tone={risk === "high" ? "danger" : risk === "medium" ? "warning" : "neutral"}>{valueLabel(risk || item.source_role || "news")}</Badge>
            <Badge tone="info">{sourceLabel(providerName(item))}</Badge>
            {text(item.evidence_type, "") ? <Badge tone="accent">{text(item.evidence_type, "")}</Badge> : null}
            {text(item.sentiment_label, "") ? <Badge tone={sentimentTone(item.sentiment_score)}>{text(item.sentiment_label, "")}</Badge> : null}
          </div>

          <section className="rounded-md border border-slate-800 bg-slate-950/50 p-4">
            <div className="text-sm font-bold text-slate-100">摘要</div>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-300">{narrativeText(item.summary, "暂无摘要")}</p>
          </section>

          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <DetailRow label="发布时间" value={text(item.published_at, "暂无")} />
            <DetailRow label="来源角色" value={valueLabel(item.source_role)} />
            <DetailRow label="热度分" value={scoreText(item.heat_score)} />
            <DetailRow label="情绪分" value={scoreText(item.sentiment_score)} />
            <DetailRow label="查询类型" value={text(item.query_type, "暂无")} />
            <DetailRow label="资讯 ID" value={newsId(item) || "暂无"} />
          </div>

          {fundCode ? (
            <div className="mt-4 rounded-md border border-cyan-500/30 bg-cyan-950/20 p-4">
              <div className="text-xs font-bold text-cyan-300">关联基金</div>
              <button type="button" className="mt-2 text-sm font-bold text-cyan-100 hover:text-cyan-200" onClick={() => onOpenFundDetail?.(fundCode)}>
                {fundCode}
              </button>
            </div>
          ) : null}

          {notes(item) ? (
            <section className="mt-4 rounded-md border border-slate-800 bg-slate-950/50 p-4">
              <div className="text-sm font-bold text-slate-100">备注</div>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-400">{notes(item)}</p>
            </section>
          ) : null}

          {sourceUrl ? (
            <div className="mt-4 space-y-2">
              <button type="button" onClick={() => void handleOpenSource()} disabled={openingUrl || !canOpenSource} className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-cyan-500/50 bg-cyan-500/15 px-3 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-500/25 disabled:cursor-not-allowed disabled:opacity-60">
                <ExternalLink className="h-4 w-4" />
                {openingUrl ? "正在打开..." : "打开原文"}
              </button>
              <div className="break-all text-xs text-slate-500">{sourceUrl}</div>
              {openError ? <div className="rounded-md border border-rose-500/40 bg-rose-950/30 p-2 text-xs text-rose-100">{openError}</div> : null}
            </div>
          ) : (
            <div className="mt-4 rounded-md border border-slate-800 bg-slate-950/50 p-3 text-sm text-slate-500">
              当前资讯没有可打开的原文链接。
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/50 p-3">
      <div className="text-xs font-bold text-slate-500">{label}</div>
      <div className="mt-1 break-words text-sm font-semibold text-slate-200">{value}</div>
    </div>
  );
}

function PanelTitle({ icon, title, badge }: { icon: ReactNode; title: string; badge?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <span className="text-cyan-300">{icon}</span>
        <div className="text-sm font-bold text-slate-100">{title}</div>
      </div>
      {badge}
    </div>
  );
}

function MiniStat({ label, value, tone }: { label: string; value: string; tone: Tone }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/40 p-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 flex items-center justify-between gap-2">
        <span className="metric-number text-sm font-bold text-slate-100">{value}</span>
        <Badge tone={tone}>{tone === "success" ? "偏正" : tone === "danger" ? "偏负" : "观察"}</Badge>
      </div>
    </div>
  );
}

function entryArray(value: unknown): ResearchDigestEntry[] {
  return Array.isArray(value) ? (value as ResearchDigestEntry[]) : [];
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function breakdownRows(value: ResearchDigestBreakdown | undefined): string[] {
  if (!value) return [];
  if (Array.isArray(value)) {
    return value.map((item) => `${providerName(item)} ${text(item.count ?? item.item_count, "0")}`).filter(Boolean);
  }
  return Object.entries(value).map(([key, count]) => `${sourceLabel(key)} ${text(count, "0")}`);
}

function providerName(item: ResearchDigestEntry): string {
  return text(item.provider ?? item.source_name ?? item.source_key ?? item.name ?? item.label, "unknown");
}

const sourceLabels: Record<string, string> = {
  eastmoney_notice_and_articles: "东方财富公告与资讯",
  "rss:chinanews_finance": "中国新闻网财经",
  eastmoney_search_api: "东方财富检索",
  "rss:chinanews_importnews": "中新网要闻",
  "rss:xinhuanet_fortune": "新华财经",
  "reg:sse_general": "上交所监管公告",
  eastmoney_nav_api: "东方财富净值接口",
  stale_snapshot: "快照滞后",
  fundgz_1234567: "基金估值接口",
  "rss:sina_fund": "新浪基金 RSS",
  xueqiu_web: "雪球网页"
};

function sourceLabel(value: unknown) {
  const raw = String(value ?? "").trim();
  return sourceLabels[raw] || raw.replace(/^rss:/, "").replace(/^reg:/, "监管 / ").replace(/_/g, " ") || "未知来源";
}

function notes(item: ResearchDigestEntry): string {
  const raw = item.notes;
  if (Array.isArray(raw)) return raw.map((entry) => String(entry)).join(" | ");
  return text(raw, "");
}

function scoreText(value: unknown): string {
  const numeric = Number(value ?? 0);
  if (!Number.isFinite(numeric)) return "0.00";
  return numeric.toFixed(2);
}

function sentimentTone(value: unknown): Tone {
  const numeric = Number(value ?? 0);
  if (numeric >= 0.15) return "success";
  if (numeric <= -0.15) return "danger";
  return "info";
}

function newsId(item: ResearchDigestEntry): string {
  return text(item.news_id ?? item.id ?? item.canonical_url ?? item.source_url ?? item.url ?? item.title, "");
}

function collectNewsItems(groups: ResearchDigestEntry[][]): ResearchDigestEntry[] {
  const seen = new Set<string>();
  const items: ResearchDigestEntry[] = [];
  for (const group of groups) {
    for (const item of group) {
      const id = newsId(item);
      if (id && seen.has(id)) continue;
      if (id) seen.add(id);
      items.push(item);
    }
  }
  return items;
}

function isHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}
