"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ChatMessage } from "@/lib/api";

type Props = { messages: ChatMessage[]; onSend: (text: string) => Promise<void>; disabled: boolean };

export default function ChatPanel({ messages, onSend, disabled }: Props) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    try {
      await onSend(text.trim());
      setText("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card chat">
      <h3>Ask the assistant</h3>
      <div className="msgs">
        {messages.length === 0 && (
          <p className="muted small">
            Try: &ldquo;move my workout to 7am&rdquo;, &ldquo;skip lunch&rdquo;, &ldquo;add call mum at 6pm for 20
            min&rdquo;, &ldquo;make workout 30 min&rdquo;.
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`msg ${m.role}`}>
            {m.content}
          </div>
        ))}
        <div ref={end} />
      </div>
      <form onSubmit={submit}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Change something in the plan…"
          disabled={disabled || busy}
        />
        <button className="primary" disabled={disabled || busy}>
          {busy ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
