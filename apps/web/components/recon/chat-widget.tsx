"use client";

import type { FormEvent, ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { RiCloseLine, RiRobot2Line, RiSendPlane2Line } from "@remixicon/react";

type ChatRole = "assistant" | "user";

type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  meta?: string;
};

type ChatResponse = {
  answer?: string;
  source?: string;
  model?: string | null;
  error?: string;
};

type ChatHistoryTurn = {
  role: ChatRole;
  content: string;
};

const GREETING =
  "Hi, I am Recon Robot. Ask me about runs, doubtful refs, daily ops, or monthly close status from stored data.";

function extractRunId(pathname: string): string | undefined {
  const match = pathname.match(/^\/runs\/([0-9a-fA-F-]{8,})/);
  return match?.[1];
}

function normalizeAssistantText(content: string): string {
  return content
    .replace(/\r/g, "")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .trim();
}

function renderAssistantContent(content: string): ReactNode {
  const lines = normalizeAssistantText(content)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length === 0) {
    return <p className="font-medium">No answer available.</p>;
  }

  return (
    <div className="space-y-1.5">
      {lines.map((line, idx) => {
        const bullet = line.match(/^[-*•]\s+(.+)$/) || line.match(/^\d+\.\s+(.+)$/);
        if (bullet) {
          return (
            <p key={`${idx}-${line.slice(0, 18)}`} className="flex items-start gap-2">
              <span className="mt-2 inline-block h-1.5 w-1.5 rounded-full bg-primary/80" />
              <span>{bullet[1]}</span>
            </p>
          );
        }
        return (
          <p key={`${idx}-${line.slice(0, 18)}`} className={idx === 0 ? "font-medium" : ""}>
            {line}
          </p>
        );
      })}
    </div>
  );
}

export function ChatWidget() {
  const pathname = usePathname();
  const runId = useMemo(() => extractRunId(pathname), [pathname]);
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content: GREETING,
    },
  ]);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = input.trim();
    if (!question || pending) return;

    setInput("");
    setError(null);
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: question,
    };
    setMessages((prev) => [...prev, userMessage]);
    setPending(true);

    try {
      const history: ChatHistoryTurn[] = messages
        .filter((message) => message.role === "assistant" || message.role === "user")
        .slice(-10)
        .map((message) => ({
          role: message.role,
          content: message.content,
        }));

      const response = await fetch("/api/v1/chat/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          run_id: runId,
          history,
        }),
      });
      const payload = (await response.json().catch(() => ({}))) as ChatResponse;
      if (!response.ok) {
        throw new Error(payload.error || "Chat request failed");
      }
      const answer = (payload.answer || "No answer available.").trim();
      const meta =
        payload.source === "system"
          ? undefined
          : [payload.source, payload.model].filter(Boolean).join(" · ");
      setMessages((prev) => [
        ...prev,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: answer,
          meta: meta || undefined,
        },
      ]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="fixed bottom-5 right-5 z-50">
      {!open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex h-14 w-14 items-center justify-center rounded-full border bg-primary text-primary-foreground shadow-xl transition hover:scale-105 hover:shadow-2xl"
          aria-label="Open recon robot chat"
        >
          <RiRobot2Line size={24} />
        </button>
      ) : (
        <section className="flex h-[34rem] w-[22rem] max-w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-2xl border bg-card shadow-2xl">
          <header className="flex items-center justify-between border-b bg-muted/40 px-3 py-2">
            <div className="flex items-center gap-2">
              <div className="rounded-full bg-primary/10 p-1 text-primary">
                <RiRobot2Line size={16} />
              </div>
              <div>
                <p className="text-sm font-medium">Recon Robot</p>
                <p className="text-[11px] text-muted-foreground">Database grounded assistant</p>
                <p className="text-[10px] text-muted-foreground/90">{runId ? `Scoped to run ${runId.slice(0, 8)}` : "Scoped to all runs"}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded border p-1 text-muted-foreground hover:text-foreground"
              aria-label="Close recon robot chat"
            >
              <RiCloseLine size={16} />
            </button>
          </header>

          <div ref={scrollRef} className="flex-1 space-y-2 overflow-y-auto px-3 py-3">
            {messages.map((message) => (
              <article
                key={message.id}
                className={`max-w-[90%] rounded-xl px-3 py-2 text-sm leading-5 ${
                  message.role === "user"
                    ? "ml-auto bg-primary text-primary-foreground whitespace-pre-wrap"
                    : "mr-auto border bg-background text-foreground"
                }`}
              >
                {message.role === "assistant" ? renderAssistantContent(message.content) : <p>{message.content}</p>}
                {message.meta ? <p className="mt-1 text-[11px] opacity-70">{message.meta}</p> : null}
              </article>
            ))}
            {pending ? (
              <article className="mr-auto rounded-xl border bg-background px-3 py-2 text-sm text-muted-foreground">
                Thinking...
              </article>
            ) : null}
          </div>

          <form onSubmit={onSubmit} className="border-t px-3 py-3">
            <div className="flex items-center gap-2">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Ask about run, ref, monthly close..."
                className="h-10 w-full rounded-lg border bg-background px-3 text-sm outline-none ring-0 focus:border-primary"
              />
              <button
                type="submit"
                disabled={pending || input.trim().length === 0}
                className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50"
                aria-label="Send message"
              >
                <RiSendPlane2Line size={16} />
              </button>
            </div>
            {error ? <p className="mt-2 text-xs text-rose-700">{error}</p> : null}
          </form>
        </section>
      )}
    </div>
  );
}
