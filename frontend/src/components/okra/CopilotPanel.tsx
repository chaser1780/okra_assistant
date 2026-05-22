import { SendHorizontal, Sparkles } from "lucide-react";
import { useState } from "react";
import { askCopilot } from "../../lib/api";
import type { CopilotResponse } from "../../lib/types";
import { Button } from "../ui";

const ASSISTANT_TITLE = "\u0052\u0041\u0047 \u52a9\u624b";
const INITIAL_ANSWER =
  "\u4f60\u53ef\u4ee5\u76f4\u63a5\u95ee\u6211\u7ec4\u5408\u3001\u57fa\u91d1\u3001\u5e02\u573a\u3001\u98ce\u9669\u6216\u8bc1\u636e\u6765\u6e90\u3002\u6211\u4f1a\u5c3d\u91cf\u7ed3\u5408 RAG \u548c\u672c\u5730\u8bc1\u636e\u56de\u7b54\u3002";
const EMPTY_ANSWER = "\u667a\u80fd\u52a9\u624b\u6682\u65f6\u6ca1\u6709\u8fd4\u56de\u53ef\u5c55\u793a\u7684\u5185\u5bb9\u3002";
const OFFLINE_ANSWER = "\u667a\u80fd\u52a9\u624b\u6682\u65f6\u4e0d\u53ef\u7528\u3002";
const QUESTION_PLACEHOLDER = "\u8f93\u5165\u4f60\u7684\u95ee\u9898\uff0c\u4f8b\u5982\uff1a\u4eca\u5929\u54ea\u4e2a\u6301\u4ed3\u7684\u98ce\u9669\u6700\u9700\u8981\u5173\u6ce8\uff1f";

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
  const [answer, setAnswer] = useState(INITIAL_ANSWER);
  const [lastResult, setLastResult] = useState<CopilotResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const trimmedQuestion = question.trim();
  const canSubmit = trimmedQuestion.length > 0 && !busy;

  async function submit() {
    if (!canSubmit) {
      return;
    }
    setBusy(true);
    try {
      const result = await askCopilot({ context, question: trimmedQuestion, page, selectedDate, fundCode });
      setAnswer(result.answer || EMPTY_ANSWER);
      setLastResult(result);
      setQuestion("");
    } catch (error) {
      setAnswer(error instanceof Error ? error.message : OFFLINE_ANSWER);
      setLastResult(null);
    } finally {
      setBusy(false);
    }
  }

  const citations = Array.isArray(lastResult?.citations) ? lastResult.citations : [];
  const retrieval = lastResult?.retrieval;

  return (
    <aside className="hidden h-full w-[320px] shrink-0 flex-col border-l border-slate-800 bg-slate-950/70 xl:flex">
      <div className="border-b border-slate-800 p-4">
        <div className="flex items-center gap-2 text-sm font-bold text-slate-100">
          <Sparkles className="h-4 w-4 text-cyan-300" />
          OKRA {ASSISTANT_TITLE}
        </div>
        <p className="mt-2 text-xs leading-5 text-slate-500">{context}</p>
      </div>
      <div className="flex-1 overflow-auto p-4">
        <div className="whitespace-pre-wrap rounded-md border border-slate-800 bg-slate-900/70 p-3 text-sm leading-6 text-slate-300">{answer}</div>
        {lastResult ? (
          <div className="mt-3 rounded-md border border-slate-800 bg-slate-950/60 p-3 text-xs leading-5 text-slate-500">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span>{lastResult.mode ?? "copilot"}</span>
              {lastResult.sourceDate ? <span>{lastResult.sourceDate}</span> : null}
              {lastResult.traceId ? <span>{lastResult.traceId}</span> : null}
              {typeof retrieval?.hitCount === "number" ? <span>{retrieval.hitCount} hits</span> : null}
            </div>
            {citations.length ? (
              <div className="mt-2 space-y-2">
                {citations.slice(0, 4).map((citation, index) => {
                  const citationId = citation.id || `C${index + 1}`;
                  const fundCodes = Array.isArray(citation.fundCodes) ? citation.fundCodes : [];
                  return (
                  <div key={citationId} className="border-t border-slate-800 pt-2">
                    <div className="font-semibold text-slate-300">
                      [{citationId}] {citation.title || citation.sourceKind || "evidence"}
                    </div>
                    <div>
                      {citation.sourceKind}
                      {citation.asOfDate ? ` | ${citation.asOfDate}` : ""}
                      {fundCodes.length ? ` | ${fundCodes.join(", ")}` : ""}
                      {citation.stale ? " | stale" : ""}
                    </div>
                  </div>
                  );
                })}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
      <div className="border-t border-slate-800 p-3">
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={QUESTION_PLACEHOLDER}
          className="h-20 w-full resize-none rounded-md border border-slate-800 bg-slate-950 p-3 text-sm text-slate-100 outline-none focus:border-cyan-700"
        />
        <Button className="mt-2 w-full gap-2" variant="primary" onClick={submit} disabled={!canSubmit}>
          <SendHorizontal className="h-4 w-4" />
          {busy ? "\u53d1\u9001\u4e2d" : "\u53d1\u9001"}
        </Button>
      </div>
    </aside>
  );
}
