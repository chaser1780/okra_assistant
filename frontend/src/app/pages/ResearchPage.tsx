import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { FundResearchCard, ResearchDigestBreakdown, ResearchDigestEntry, ResearchPayload, ResearchSentimentBlock, Tone } from "../../lib/types";
import { asNullableNumber, asNumber, text } from "../../lib/format";
import { actionLabel, narrativeText, roleLabel, styleLabel, valueLabel } from "../../lib/display";
import { Activity, ArrowRight, FileText, Newspaper, RadioTower, Search, ShieldAlert } from "lucide-react";
import { Badge, Button, Card, EmptyState, MetricCard, SectionTitle } from "../../components/ui";
import { TerminalPanel, TerminalState } from "../../components/okra/TerminalChrome";

export function ResearchPage({ research, onOpenFundDetail }: { research: ResearchPayload; onOpenFundDetail?: (fundCode: string) => void }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "actionable" | "watch" | "conflict">("all");
  const [selectedTicketId, setSelectedTicketId] = useState("");
  const cards = useMemo(() => {
    const source = research.fund_cards?.length ? research.fund_cards : research.rows.map(rowToFundCard);
    const needle = query.trim().toLowerCase();
    return source.filter((card) => {
      const searchText = [
        card.fundName,
        card.fundCode,
        card.actionLabel,
        card.thesis,
        card.profile.category,
        card.portfolio.styleGroup,
        card.news.topTitle,
        card.news.topRiskTitle
      ].filter(Boolean).join(" ").toLowerCase();
      const matchesQuery = !needle || searchText.includes(needle);
      const matchesFilter = filter === "all" || (filter === "actionable" ? card.isActionable : filter === "watch" ? !card.isActionable : card.hasConflict);
      return matchesQuery && matchesFilter;
    });
  }, [filter, query, research.fund_cards, research.rows]);
  const selectedCard = useMemo(() => {
    if (!cards.length) return null;
    return cards.find((card) => card.ticketId === selectedTicketId) ?? cards[0];
  }, [cards, selectedTicketId]);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {research.metrics.map((metric) => (
          <MetricCard key={metric.title} {...metric} value={narrativeText(metric.value, "0")} body={narrativeText(metric.body, "暂无说明")} />
        ))}
      </div>
      <ResearchAnalytics cards={cards} />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <SourceHealthPanel sourceHealth={research.source_health} />
        <NewsDigestPanel digest={research.news_digest} eventRisks={research.event_risks} />
        <SentimentDigestPanel digest={research.sentiment_digest} />
      </div>

      <Card className="p-0">
        <div className="grid min-h-[640px] grid-cols-1 overflow-hidden lg:grid-cols-[360px_minmax(0,1fr)]">
          <aside className="border-b border-slate-800 bg-slate-950/35 lg:border-b-0 lg:border-r">
            <div className="border-b border-slate-800 p-4">
              <SectionTitle title="建议卡" meta={research.meta} />
              <div className="flex h-9 items-center gap-2 rounded-md border border-slate-800 bg-slate-950 px-3 text-sm text-slate-400 focus-within:border-cyan-700">
                <Search className="h-4 w-4 shrink-0" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索基金、动作、风险"
                  className="h-full min-w-0 flex-1 bg-transparent text-slate-100 outline-none placeholder:text-slate-600"
                />
              </div>
              <div className="mt-3 grid grid-cols-4 gap-1 rounded-md border border-slate-800 bg-slate-950 p-1">
                {([
                  ["all", "全部"],
                  ["actionable", "可执行"],
                  ["watch", "观察"],
                  ["conflict", "分歧"]
                ] as const).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setFilter(key)}
                    className={`h-7 rounded-sm text-[11px] font-semibold transition ${filter === key ? "bg-cyan-500/20 text-cyan-100" : "text-slate-500 hover:text-slate-200"}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            {cards.length ? (
              <div className="max-h-[590px] overflow-y-auto p-2">
                {cards.map((card) => (
                  <TicketButton
                    key={card.ticketId}
                    card={card}
                    selected={card.ticketId === selectedCard?.ticketId}
                    onClick={() => setSelectedTicketId(card.ticketId)}
                  />
                ))}
              </div>
            ) : (
              <div className="p-4">
                <EmptyState title="暂无基金 Ticket" body="运行今日分析后，这里会按基金生成每日建议卡。" />
              </div>
            )}
          </aside>

          {selectedCard ? (
            <FundTicketWorkspace card={selectedCard} onOpenFundDetail={onOpenFundDetail} />
          ) : (
            <div className="p-5">
              <EmptyState title="暂无研究建议" body="运行今日分析后，这里会显示加仓、定投和观察建议。" />
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

function ResearchAnalytics({ cards }: { cards: FundResearchCard[] }) {
  const counts = cards.reduce<Record<string, number>>((acc, card) => { const label = actionLabel(card.action); acc[label] = (acc[label] ?? 0) + 1; return acc; }, {});
  const averageConfidence = cards.length ? cards.reduce((sum, card) => sum + Number(card.confidence || 0), 0) / cards.length : 0;
  const evidenceCount = cards.reduce((sum, card) => sum + card.evidence.length, 0);
  return (
    <TerminalPanel title="研究信号" meta={`${cards.length} 张建议卡`} className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-[1.2fr_1fr_1fr]">
      <div><div className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">动作分布</div><div className="space-y-2">{Object.entries(counts).map(([label, count]) => <div key={label}><div className="mb-1 flex justify-between text-xs"><span className="text-slate-300">{label}</span><span className="tabular-nums text-slate-500">{count}</span></div><div className="h-1.5 bg-slate-900"><div className="h-full bg-cyan-300" style={{ width: `${cards.length ? count / cards.length * 100 : 0}%` }} /></div></div>)}{!cards.length ? <span className="text-xs text-slate-600">暂无动作数据</span> : null}</div></div>
      <div><div className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">置信度</div><div className="metric-number text-3xl font-semibold text-cyan-200">{(averageConfidence * 100).toFixed(0)}%</div><div className="mt-3 h-2 bg-slate-900"><div className="h-full bg-cyan-300" style={{ width: `${Math.max(0, Math.min(100, averageConfidence * 100))}%` }} /></div><div className="mt-2 text-xs text-slate-600">建议卡平均置信度</div></div>
      <div><div className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">证据密度</div><div className="metric-number text-3xl font-semibold text-slate-100">{evidenceCount}</div><div className="mt-2 text-xs text-slate-500">结构化证据</div><div className="mt-3"><TerminalState label={cards.some((card) => card.hasConflict) ? "存在分歧" : "无明显分歧"} tone={cards.some((card) => card.hasConflict) ? "warning" : "success"} /></div></div>
    </TerminalPanel>
  );
}

function TicketButton({ card, selected, onClick }: { card: FundResearchCard; selected: boolean; onClick: () => void }) {
  const pnlTone = toneFromNumber(card.portfolio.holdingPnl);
  const changeTone = toneFromNumber(card.market.estimateChangePct ?? card.market.dayChangePct ?? card.market.proxyChangePct);
  return (
    <button
      type="button"
      onClick={onClick}
      className={`mb-2 w-full rounded-md border p-3 text-left transition ${
        selected ? "border-cyan-500/60 bg-cyan-950/30" : "border-slate-800 bg-slate-950/50 hover:border-slate-700 hover:bg-slate-900/70"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-bold text-slate-100">{card.fundName}</div>
          <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
            <span className="metric-number">{card.fundCode}</span>
            <span>{styleLabel(card.portfolio.styleGroup)}</span>
          </div>
        </div>
        <Badge tone={actionTone(card.action)}>{actionLabel(card.action)}</Badge>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <TicketStat label="金额" value={card.amountText || "0.00"} />
        <TicketStat label="收益" value={text(card.portfolio.holdingPnlText, "0.00")} tone={pnlTone} />
        <TicketStat label="信号" value={text(card.market.estimateChangePctText, text(card.market.dayChangePctText, "暂无"))} tone={changeTone} />
      </div>
      <p className="mt-3 line-clamp-2 text-xs leading-5 text-slate-500">{narrativeText(card.thesis)}</p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {card.hasConflict ? <Badge tone="warning">分歧</Badge> : <Badge tone="success">{card.consensusText || "共识"}</Badge>}
        {card.news.riskCount ? <Badge tone="danger">新闻风险 {card.news.riskCount}</Badge> : null}
        {card.policyRuleHits.length ? <Badge tone="purple">规则 {card.policyRuleHits.length}</Badge> : null}
      </div>
    </button>
  );
}

function TicketStat({ label, value, tone = "neutral" }: { label: string; value: string; tone?: Tone }) {
  const toneClass =
    tone === "success" ? "text-emerald-200" : tone === "danger" ? "text-rose-200" : tone === "warning" ? "text-amber-200" : "text-slate-200";
  return (
    <div className="rounded border border-slate-800 bg-slate-950/70 px-2 py-1.5">
      <div className="text-[11px] text-slate-600">{label}</div>
      <div className={`metric-number mt-1 truncate font-semibold ${toneClass}`}>{value}</div>
    </div>
  );
}

function FundTicketWorkspace({ card, onOpenFundDetail }: { card: FundResearchCard; onOpenFundDetail?: (fundCode: string) => void }) {
  return (
    <main className="min-w-0">
      <div className="border-b border-slate-800 bg-slate-950/20 px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={actionTone(card.action)}>{actionLabel(card.action)}</Badge>
              <Badge tone={card.hasConflict ? "warning" : "success"}>{card.consensusText || "暂无共识"}</Badge>
              {card.news.riskCount ? <Badge tone="danger">新闻风险 {card.news.riskCount}</Badge> : null}
              {card.portfolio.allowTrade === false ? <Badge tone="warning">不可交易</Badge> : null}
            </div>
            <h2 className="mt-3 truncate text-xl font-black text-slate-50">{card.fundName}</h2>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-500">
              <span className="metric-number">{card.fundCode}</span>
              <span>|</span>
              <span>{roleLabel(card.portfolio.role)}</span>
              <span>|</span>
              <span>{styleLabel(card.portfolio.styleGroup)}</span>
              <span>|</span>
              <span>{card.selectedDate}</span>
            </div>
          </div>
          {onOpenFundDetail ? (
            <Button variant="primary" className="shrink-0 gap-2" onClick={() => onOpenFundDetail(card.fundCode)}>
              完整详情
              <ArrowRight className="h-4 w-4" />
            </Button>
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 border-b border-slate-800 px-5 py-4 md:grid-cols-2 xl:grid-cols-4">
        <SignalTile label="建议金额" value={card.amountText || "0.00"} helper={`优先级 ${card.priority || 0}`} />
        <SignalTile
          label="持仓盈亏"
          value={text(card.portfolio.holdingPnlText, "0.00")}
          helper={text(card.portfolio.holdingReturnPctText, "0.00%")}
          tone={toneFromNumber(card.portfolio.holdingPnl)}
        />
        <SignalTile
          label="估算涨跌"
          value={text(card.market.estimateChangePctText, "暂无")}
          helper={text(card.market.estimateFreshness, "估算数据")}
          tone={toneFromNumber(card.market.estimateChangePct)}
        />
        <SignalTile
          label="代理涨跌"
          value={text(card.market.proxyChangePctText, "暂无")}
          helper={text(card.market.proxyFreshness, "代理数据")}
          tone={toneFromNumber(card.market.proxyChangePct)}
        />
      </div>

      <div className="grid grid-cols-12 gap-4 p-5">
        <section className="col-span-12 space-y-4 xl:col-span-7">
          <Panel title="建议卡" icon={<FileText className="h-4 w-4" />}>
            <p className="text-sm leading-7 text-slate-300">{narrativeText(card.thesis)}</p>
            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
            <KeyValue label="动作" value={actionLabel(card.action)} />
              <KeyValue label="置信度" value={card.confidenceText || "暂无"} />
              <KeyValue label="组合市值" value={text(card.portfolio.currentValueText, "0.00")} />
              <KeyValue label="官方净值" value={`${text(card.market.officialNav, "暂无")} ${card.market.officialNavDate ? `(${card.market.officialNavDate})` : ""}`} />
            </div>
          </Panel>

          <Panel title="证据与风险" icon={<ShieldAlert className="h-4 w-4" />}>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <CompactList title="有效证据" items={card.evidence} empty="暂无结构化证据" />
              <CompactList title="风险提示" items={card.risks} empty="暂无突出风险" />
            </div>
          </Panel>

          <Panel title="规则和信号" icon={<Activity className="h-4 w-4" />}>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <CompactList title="策略规则" items={card.policyRuleHits} empty="暂无命中规则" code />
              <CompactList title="硬约束" items={card.constraintHits} empty="暂无命中约束" code />
              <CompactList title="支持信号" items={card.sourceSignalIds} empty="暂无支持信号" code />
              <CompactList title="反向信号" items={card.opposingSignalIds} empty="暂无反向信号" code />
            </div>
          </Panel>
        </section>

        <aside className="col-span-12 space-y-4 xl:col-span-5">
          <Panel title="市场信号" icon={<Activity className="h-4 w-4" />}>
            <div className="space-y-2">
              <KeyValue label="官方日涨跌" value={text(card.market.dayChangePctText, "暂无")} tone={toneFromNumber(card.market.dayChangePct)} />
              <KeyValue label="估算日涨跌" value={text(card.market.estimateChangePctText, "暂无")} tone={toneFromNumber(card.market.estimateChangePct)} />
              <KeyValue label="代理日涨跌" value={text(card.market.proxyChangePctText, "暂无")} tone={toneFromNumber(card.market.proxyChangePct)} />
              <KeyValue label="估算时间" value={text(card.market.estimateTime, "暂无")} />
            </div>
          </Panel>

          <Panel title="新闻风险" icon={<Newspaper className="h-4 w-4" />}>
            <NewsList items={(card.news.riskItems?.length ? card.news.riskItems : card.news.items) ?? []} />
          </Panel>

          <Panel title="基金画像" icon={<RadioTower className="h-4 w-4" />}>
            <div className="space-y-2">
              <KeyValue label="基金经理" value={text(card.profile.manager, "暂无")} />
              <KeyValue label="管理人" value={text(card.profile.company, "暂无")} />
              <KeyValue label="分类" value={text(card.profile.category, "暂无")} />
              <KeyValue label="基准" value={text(card.profile.benchmark, "暂无")} />
            </div>
          </Panel>
        </aside>
      </div>
    </main>
  );
}

function SignalTile({ label, value, helper, tone = "neutral" }: { label: string; value: string; helper: string; tone?: Tone }) {
  const color = tone === "success" ? "text-emerald-200" : tone === "danger" ? "text-rose-200" : tone === "warning" ? "text-amber-200" : "text-slate-100";
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/55 p-3">
      <div className="text-xs font-bold text-slate-500">{label}</div>
      <div className={`metric-number mt-2 truncate text-lg font-black ${color}`}>{value}</div>
      <div className="mt-1 truncate text-xs text-slate-600">{helper}</div>
    </div>
  );
}

function Panel({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-md border border-slate-800 bg-slate-950/45 p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-cyan-300">{icon}</span>
        <h3 className="text-sm font-bold text-slate-100">{title}</h3>
      </div>
      {children}
    </section>
  );
}

function KeyValue({ label, value, tone = "neutral" }: { label: string; value: string; tone?: Tone }) {
  const color = tone === "success" ? "text-emerald-200" : tone === "danger" ? "text-rose-200" : tone === "warning" ? "text-amber-200" : "text-slate-200";
  return (
    <div className="flex items-start justify-between gap-3 rounded border border-slate-800 bg-slate-950/55 px-3 py-2 text-sm">
      <span className="shrink-0 text-slate-500">{label}</span>
      <span className={`metric-number text-right font-semibold ${color}`}>{value}</span>
    </div>
  );
}

function CompactList({ title, items, empty, code = false }: { title: string; items: string[]; empty: string; code?: boolean }) {
  const rows = items.length ? items : [empty];
  return (
    <div>
      <div className="mb-2 text-sm font-bold text-slate-200">{title}</div>
      <ul className="space-y-2 text-sm leading-6 text-slate-400">
        {rows.slice(0, 6).map((item, index) => (
          <li key={`${title}-${index}`} className={code ? "break-all font-mono text-xs text-slate-500" : ""}>
            - {code ? narrativeText(item, item) : narrativeText(item, item)}
          </li>
        ))}
      </ul>
    </div>
  );
}

function NewsList({ items }: { items: ResearchDigestEntry[] }) {
  if (!items.length) return <p className="text-sm leading-6 text-slate-500">暂无直接关联新闻。</p>;
  return (
    <div className="space-y-3">
      {items.slice(0, 4).map((item, index) => (
        <div key={text(item.news_id ?? item.id, `news-${index}`)} className="rounded border border-slate-800 bg-slate-950/55 p-3">
            <div className="line-clamp-2 text-sm font-semibold leading-6 text-slate-200">{narrativeText(item.title, "暂无标题")}</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge tone={newsTone(item)}>{text(item.risk_level ?? item.impact ?? item.sentiment_label, "news")}</Badge>
            {item.heat_score !== undefined ? <Badge tone="info">热度 {text(item.heat_score, "0")}</Badge> : null}
          </div>
            <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">{narrativeText(item.summary, "暂无摘要")}</p>
        </div>
      ))}
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
        `预警 ${warningCount} / 错误 ${errorCount}`,
        ...warningItems.map((item) => `${sourceLabel(item.source_key)}：${valueLabel(item.status)}`)
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
        highlightHeat ? `热点 ${newsHeadline(highlightHeat)}` : highlightRisk ? `风险 ${newsHeadline(highlightRisk)}` : "暂无热点新闻摘要"
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
         health.length ? `${sourceLabel(providerName(health[0]))}：${valueLabel(health[0].status)}` : disabledSources.length ? `停用来源 ${disabledSources.map(sourceLabel).join("、")}` : ""
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
            {humanizeSourceText(row)}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function rowToFundCard(row: Record<string, unknown>): FundResearchCard {
  const code = text(row.fund_code ?? row.fundCode, "");
  const action = text(row.validated_action ?? row.action, "hold");
  const amount = asNullableNumber(row.validated_amount);
  return {
    ticketId: text(row.suggestion_id, code || "ticket"),
    fundCode: code,
    fundName: text(row.fund_name ?? row.fundName, code),
    selectedDate: "",
    section: text(row._section, ""),
    strategyBucket: text(row.strategy_bucket, ""),
    action,
    actionLabel: actionLabel(action),
    amount,
    amountText: amount === null ? "不可用" : amount.toFixed(2),
    priority: asNumber(row.priority),
    confidence: asNumber(row.confidence),
    confidenceText: asNumber(row.confidence).toFixed(2),
    thesis: text(row.thesis ?? row.reason, "暂无建议理由"),
    evidence: normalizeStringArray(row.evidence),
    risks: normalizeStringArray(row.risks),
    agentSupport: normalizeStringArray(row.agent_support),
    sourceSignalIds: normalizeStringArray(row.source_signal_ids),
    opposingSignalIds: normalizeStringArray(row.opposing_signal_ids),
    policyRuleHits: normalizeStringArray(row.policy_rule_hits),
    constraintHits: normalizeStringArray(row.constraint_hits),
    consensusText: text(row._consensus_text, "暂无"),
    hasConflict: Boolean(row._has_conflict),
    isActionable: action !== "hold" && action !== "not_applicable",
    portfolio: {},
    market: {},
    news: { items: [], riskItems: [], count: 0, riskCount: 0 },
    profile: {},
    evidenceRefs: []
  };
}

function normalizeStringArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean);
  if (typeof value === "string") return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
  return [];
}

function actionTone(action: string): Tone {
  if (["buy", "add", "scheduled_dca", "planned_dca"].includes(action)) return "accent";
  if (["sell", "reduce", "switch", "switch_out"].includes(action)) return "danger";
  if (action === "locked" || action === "not_applicable") return "warning";
  return "neutral";
}

function toneFromNumber(value: unknown): Tone {
  const parsed = asNumber(value);
  if (parsed > 0) return "success";
  if (parsed < 0) return "danger";
  return "neutral";
}

const sourceLabels: Record<string, string> = {
  eastmoney_notice_and_articles: "东方财富公告与资讯",
  "rss:chinanews_finance": "中国新闻网财经",
  eastmoney_search_api: "东方财富检索",
  "rss:chinanews_importnews": "中新网要闻",
  "rss:xinhuanet_fortune": "新华财经",
  "reg:sse_general": "上交所监管公告",
  eastmoney_nav_api: "东方财富净值接口",
  fundgz_1234567: "基金估值接口",
  "rss:sina_fund": "新浪基金 RSS",
  xueqiu_web: "雪球网页"
};

function sourceLabel(value: unknown) {
  const raw = String(value ?? "").trim();
  return sourceLabels[raw] || raw.replace(/^rss:/, "").replace(/^reg:/, "监管 / ").replace(/_/g, " ") || "未知来源";
}

function humanizeSourceText(value: string) {
  let result = narrativeText(value, value);
  for (const [key, label] of Object.entries(sourceLabels)) result = result.split(key).join(label);
  return result
    .replace(/quotes:/gi, "行情 / ")
    .replace(/\bnone\b/gi, "未分类")
    .replace(/\btheme\b/gi, "主题")
    .replace(/\bdirect\b/gi, "直接")
    .replace(/\bmarket_derived\b/gi, "市场派生")
    .replace(/\bllm_first\b/gi, "模型优先")
    .replace(/\benabled\b/gi, "已启用")
    .replace(/\bdisabled\b/gi, "已停用")
    .replace(/\bwarning\b/gi, "预警")
    .replace(/\berror\b/gi, "错误")
    .replace(/\bok\b/gi, "正常");
}

function newsTone(item: ResearchDigestEntry): Tone {
  const value = text(item.risk_level ?? item.impact ?? item.sentiment_label, "").toLowerCase();
  if (["high", "negative"].includes(value)) return "danger";
  if (["medium", "mixed"].includes(value)) return "warning";
  if (["positive", "low"].includes(value)) return "success";
  return "neutral";
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
