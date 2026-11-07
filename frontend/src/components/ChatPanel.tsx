"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ChatMessage } from "@/lib/api";

type Props = { messages: ChatMessage[]; onSend: (text: string) => Promise<void>; disabled: boolean };

export default function ChatPanel({ messages, onSend, disabled }: Props) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (el) el.scrollTop = el.scrollHeight;
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
    <div className="sheet chat">
      <h3>Change the plan</h3>
      <div className="msgs" ref={box}>
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
      </div>
      <form onSubmit={submit}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Change something in the plan…"
          disabled={disabled || busy}
        />
        <button className="primary" disabled={disabled || busy}>
          {busy ? "Sending" : "Send"}
        </button>
      </form>
    </div>
  );
}
