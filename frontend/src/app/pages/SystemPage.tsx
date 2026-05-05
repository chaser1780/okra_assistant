import { fieldLabel, valueLabel } from "../../lib/display";
import { Badge, Card, SectionTitle } from "../../components/ui";

export function SystemPage({ system, summary }: { system: Record<string, unknown>; summary: Record<string, unknown> }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <Card className="p-4">
        <SectionTitle title="系统摘要" />
        <KeyValueTree value={summary} />
      </Card>
      <Card className="p-4">
        <SectionTitle title="运行与数据源" />
        <KeyValueTree value={system} />
      </Card>
    </div>
  );
}

function KeyValueTree({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (Array.isArray(value)) {
    if (!value.length) return <div className="text-sm text-slate-500">暂无</div>;
    return (
      <div className="space-y-2">
        {value.map((item, index) => (
          <div key={index} className="rounded-md border border-slate-800 bg-slate-950/40 p-2">
            <KeyValueTree value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (!entries.length) return <div className="text-sm text-slate-500">暂无</div>;
    return (
      <div className="space-y-2">
        {entries.map(([key, item]) => (
          <div key={key} className={depth ? "border-b border-slate-800/70 pb-2" : "rounded-md border border-slate-800 bg-slate-950/40 p-3"}>
            <div className="mb-1 flex items-center justify-between gap-3 text-sm">
              <span className="font-semibold text-slate-300">{fieldLabel(key)}</span>
              {!isNested(item) ? <ValueBadge value={item} /> : null}
            </div>
            {isNested(item) ? <KeyValueTree value={item} depth={depth + 1} /> : null}
          </div>
        ))}
      </div>
    );
  }
  return <ValueBadge value={value} />;
}

function ValueBadge({ value }: { value: unknown }) {
  const label = valueLabel(value);
  if (label === "正常" || label === "是" || label === "成功" || label === "新鲜") return <Badge tone="success">{label}</Badge>;
  if (label === "注意" || label === "已过期" || label === "兜底") return <Badge tone="warning">{label}</Badge>;
  if (label === "错误" || label === "失败") return <Badge tone="danger">{label}</Badge>;
  return <span className="break-all text-right text-sm text-slate-400">{label}</span>;
}

function isNested(value: unknown) {
  return Boolean(value && typeof value === "object");
}
