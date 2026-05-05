import { SendHorizontal, Sparkles } from "lucide-react";
import { useState } from "react";
import { askCopilot } from "../../lib/api";
import { Button } from "../ui";

export function CopilotPanel({
  context,
  page,
  selectedDate,
  fundCode
}: {
  context: string;
  page: string;
  selectedDate?: string;
  fundCode?: string;
}) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("我会根据当前页面解释建议、风险和证据链。选中一只基金或输入问题后，我会把结论讲清楚。");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      const result = await askCopilot({ context, question, page, selectedDate, fundCode });
      setAnswer(result.answer);
      setQuestion("");
    } catch (error) {
      setAnswer(error instanceof Error ? error.message : "智能助手暂时不可用。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="flex h-full w-[320px] shrink-0 flex-col border-l border-slate-800 bg-slate-950/70">
      <div className="border-b border-slate-800 p-4">
        <div className="flex items-center gap-2 text-sm font-bold text-slate-100">
          <Sparkles className="h-4 w-4 text-cyan-300" />
          OKRA 智能助手
        </div>
        <p className="mt-2 text-xs leading-5 text-slate-500">{context}</p>
      </div>
      <div className="flex-1 overflow-auto p-4">
        <div className="whitespace-pre-wrap rounded-md border border-slate-800 bg-slate-900/70 p-3 text-sm leading-6 text-slate-300">{answer}</div>
      </div>
      <div className="border-t border-slate-800 p-3">
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="例如：为什么今天建议减仓这只基金？"
          className="h-20 w-full resize-none rounded-md border border-slate-800 bg-slate-950 p-3 text-sm text-slate-100 outline-none focus:border-cyan-700"
        />
        <Button className="mt-2 w-full gap-2" variant="primary" onClick={submit} disabled={busy}>
          <SendHorizontal className="h-4 w-4" />
          {busy ? "正在解释" : "解释当前页面"}
        </Button>
      </div>
    </aside>
  );
}
