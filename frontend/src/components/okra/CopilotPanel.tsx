import { PanelRightClose, PanelRightOpen, SendHorizontal, Sparkles, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { askCopilot } from "../../lib/api";
import type { CopilotMessage, CopilotResponse } from "../../lib/types";
import { Button } from "../ui";

const ASSISTANT_TITLE = "\u667a\u80fd\u95ee\u7b54";
const INITIAL_ANSWER = "\u4f60\u53ef\u4ee5\u76f4\u63a5\u95ee\u6211\u7ec4\u5408\u3001\u57fa\u91d1\u3001\u5e02\u573a\u3001\u98ce\u9669\u6216\u8bc1\u636e\u6765\u6e90\u3002";
const EMPTY_ANSWER = "\u667a\u80fd\u52a9\u624b\u6682\u65f6\u6ca1\u6709\u8fd4\u56de\u53ef\u5c55\u793a\u7684\u5185\u5bb9\u3002";
const OFFLINE_ANSWER = "\u667a\u80fd\u52a9\u624b\u6682\u65f6\u4e0d\u53ef\u7528\u3002";
const STOPPED_ANSWER = "\u5df2\u505c\u6b62\u672c\u6b21\u56de\u7b54\u3002";
const QUESTION_PLACEHOLDER = "\u8f93\u5165\u4f60\u7684\u95ee\u9898";
const HISTORY_LIMIT = 10;

type UiMessage = CopilotMessage & {
  id: string;
};

function newMessageId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function CopilotPanel({
  open,
  onToggle,
  context,
  page,
  selectedDate,
  fundCode
}: {
  open: boolean;
  onToggle: () => void;
  context: string;
  page: string;
  selectedDate?: string;
  fundCode?: string;
}) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<UiMessage[]>([{ id: "initial", role: "assistant", content: INITIAL_ANSWER }]);
  const [lastResult, setLastResult] = useState<CopilotResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const trimmedQuestion = question.trim();
  const canSubmit = trimmedQuestion.length > 0 && !busy;

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ block: "end" });
  }, [messages, busy]);

  async function submit() {
    if (!canSubmit) {
      return;
    }
    const userMessage: UiMessage = { id: newMessageId(), role: "user", content: trimmedQuestion };
    const nextMessages = [...messages, userMessage];
    const controller = new AbortController();
    abortRef.current = controller;
    setMessages(nextMessages);
    setBusy(true);
    try {
      const history = nextMessages.slice(-HISTORY_LIMIT).map(({ role, content }) => ({ role, content }));
      const result = await askCopilot({ context, question: trimmedQuestion, page, selectedDate, fundCode, messages: history }, controller.signal);
      const answer = result.answer || EMPTY_ANSWER;
      setMessages((current) => [...current, { id: newMessageId(), role: "assistant", content: answer }]);
      setLastResult(result);
      setQuestion("");
    } catch (error) {
      const stopped = error instanceof DOMException && error.name === "AbortError";
      setMessages((current) => [
        ...current,
        { id: newMessageId(), role: "assistant", content: stopped ? STOPPED_ANSWER : error instanceof Error ? error.message : OFFLINE_ANSWER }
      ]);
      setLastResult(null);
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setBusy(false);
      }
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  const citations = Array.isArray(lastResult?.citations) ? lastResult.citations : [];
  const retrieval = lastResult?.retrieval;
  const quickPrompts = page === "today"
    ? ["今天有哪些可执行动作？", "组合当前最大的风险是什么？"]
    : page === "portfolio"
      ? ["组合的最大风格暴露是什么？", "哪些持仓需要重点关注？"]
      : page === "realtime"
        ? ["哪些估值已经滞后？", "当前实时收益最主要由谁贡献？"]
        : page === "research"
          ? ["为什么建议这只基金？", "哪些规则阻止了加仓？"]
          : ["请解释当前页面的重点。", "有哪些证据值得优先查看？"];

  if (!open) {
    return (
      <button
        type="button"
        className="hidden h-full w-11 shrink-0 items-start justify-center border-l border-slate-800 bg-slate-950/80 pt-5 text-slate-400 transition hover:bg-slate-900 hover:text-cyan-200 xl:flex"
        onClick={onToggle}
        aria-label="展开智能问答"
        title="展开智能问答"
      >
        <PanelRightOpen className="h-4 w-4" />
      </button>
    );
  }

  return (
    <aside className="hidden h-full w-[320px] shrink-0 flex-col border-l border-slate-800 bg-slate-950/80 xl:flex">
      <div className="border-b border-slate-800 p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm font-bold text-slate-100">
          <Sparkles className="h-4 w-4 text-cyan-300" />
          OKRA {ASSISTANT_TITLE}
          </div>
          <button type="button" className="rounded-sm p-1.5 text-slate-500 transition hover:bg-slate-900 hover:text-slate-100" onClick={onToggle} aria-label="收起智能问答" title="收起智能问答">
            <PanelRightClose className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-2 text-xs leading-5 text-slate-500">{context}</p>
      </div>
      <div className="flex-1 space-y-3 overflow-auto p-4">
        {messages.length === 1 && !busy ? (
          <div className="rounded-md border border-cyan-500/20 bg-cyan-950/15 p-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-cyan-300/80">快速提问</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {quickPrompts.map((prompt) => (
                <button key={prompt} type="button" className="rounded-sm border border-slate-700 bg-slate-950/70 px-2 py-1.5 text-xs text-slate-300 transition hover:border-cyan-500/50 hover:text-cyan-100" onClick={() => setQuestion(prompt)}>
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {messages.map((message) => (
          <div key={message.id} className={message.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div
              className={
                message.role === "user"
                  ? "max-w-[92%] whitespace-pre-wrap rounded-md border border-cyan-500/40 bg-cyan-950/35 p-3 text-sm leading-6 text-cyan-50"
                  : "max-w-[92%] whitespace-pre-wrap rounded-md border border-slate-800 bg-slate-900/70 p-3 text-sm leading-6 text-slate-300"
              }
            >
              {message.content}
            </div>
          </div>
        ))}
        {busy ? (
          <div className="flex justify-start">
            <div className="rounded-md border border-slate-800 bg-slate-900/70 px-3 py-2 text-sm text-slate-400">\u601d\u8003\u4e2d...</div>
          </div>
        ) : null}
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
        <div ref={scrollRef} />
      </div>
      <div className="border-t border-slate-800 p-3">
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              void submit();
            }
          }}
          placeholder={QUESTION_PLACEHOLDER}
          className="h-20 w-full resize-none rounded-md border border-slate-800 bg-slate-950 p-3 text-sm text-slate-100 outline-none focus:border-cyan-700"
        />
        <Button className="mt-2 w-full gap-2" variant={busy ? "danger" : "primary"} onClick={busy ? stop : submit} disabled={!busy && !canSubmit}>
          {busy ? <Square className="h-4 w-4" /> : <SendHorizontal className="h-4 w-4" />}
          {busy ? "\u6682\u505c" : "\u53d1\u9001"}
        </Button>
      </div>
    </aside>
  );
}
