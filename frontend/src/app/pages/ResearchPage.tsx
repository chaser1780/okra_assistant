import { useMemo, useState } from "react";
import type { ResearchPayload } from "../../lib/types";
import { text } from "../../lib/format";
import { actionLabel } from "../../lib/display";
import { Badge, Card, EmptyState, MetricCard, SectionTitle } from "../../components/ui";

export function ResearchPage({ research }: { research: ResearchPayload }) {
  const [query, setQuery] = useState("");
  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return research.rows;
    return research.rows.filter((row) => JSON.stringify(row).toLowerCase().includes(needle));
  }, [query, research.rows]);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-4">
        {research.metrics.map((metric) => (
          <MetricCard key={metric.title} {...metric} />
        ))}
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
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={`${text(row.fund_code, "row")}-${index}`} className="border-t border-slate-800 text-slate-300">
                    <td className="px-3 py-3">
                      <div className="font-semibold text-slate-100">{text(row.fund_name, text(row.fund_code))}</div>
                      <div className="text-xs text-slate-500">{text(row.fund_code, "")}</div>
                    </td>
                    <td className="px-3 py-3">
                      <Badge tone={text(row.validated_action, "hold") === "hold" ? "neutral" : "accent"}>{actionLabel(row.validated_action)}</Badge>
                    </td>
                    <td className="metric-number px-3 py-3 text-right">{text(row.validated_amount, "0")}</td>
                    <td className="px-3 py-3">
                      <Badge tone={row._has_conflict ? "warning" : "success"}>{text(row._consensus_text, "暂无")}</Badge>
                    </td>
                    <td className="max-w-xl px-3 py-3 text-slate-400">{text(row.thesis || row.reason, "暂无理由")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="暂无研究建议" body="运行首启分析后，这里会显示加仓、定投和观察建议。" />
        )}
      </Card>
    </div>
  );
}
