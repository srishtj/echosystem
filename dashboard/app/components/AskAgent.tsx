'use client';

import { useEffect, useRef, useState } from 'react';
import { API_URL, apiFetch } from '../lib/api';

type Source = { tool: string; input: Record<string, unknown>; output: string };
type Message =
  | { role: 'user'; content: string }
  | { role: 'assistant'; content: string; auditStatus: string; retryCount: number; sources: Source[] }
  | { role: 'error'; content: string };

const TOOL_LABELS: Record<string, string> = {
  hybrid_search: 'Knowledge graph',
  get_stock_data: 'Stock data',
  get_sec_snapshot: 'SEC filings',
  search_reddit: 'Reddit',
};

export default function AskAgent() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  async function ask() {
    const q = question.trim();
    if (!q || loading) return;
    setMessages((m) => [...m, { role: 'user', content: q }]);
    setQuestion('');
    setLoading(true);
    try {
      const res = await apiFetch(`${API_URL}/api/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: data.answer,
          auditStatus: data.audit_status,
          retryCount: data.retry_count,
          sources: data.sources ?? [],
        },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: 'error', content: e instanceof Error ? e.message : 'Request failed' },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-2xl border border-hairline bg-paper p-6 shadow-[0_1px_2px_rgba(42,30,23,0.04),0_20px_40px_-24px_rgba(122,31,46,0.4)]">
      <h2 className="mb-1 font-serif text-2xl font-semibold text-ink">Ask EchoSystem</h2>
      <p className="mb-4 text-sm leading-relaxed text-ink-muted">
        Ask a plain-language question. The agent pulls from the knowledge graph, stock data, SEC
        filings, and Reddit as needed, and a second model audits the answer before you see it.
      </p>

      {messages.length > 0 && (
        <div className="mb-4 max-h-[420px] space-y-3 overflow-y-auto rounded-xl border border-hairline bg-cream p-4">
          {messages.map((m, i) => {
            if (m.role === 'user') {
              return (
                <div key={i} className="flex justify-end">
                  <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-accent px-4 py-2 text-sm text-cream">
                    {m.content}
                  </div>
                </div>
              );
            }
            if (m.role === 'error') {
              return (
                <div key={i} className="rounded-xl bg-negative-soft px-4 py-2 text-sm text-negative">
                  Couldn&apos;t get an answer: {m.content}
                </div>
              );
            }
            return (
              <div key={i} className="flex justify-start">
                <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-hairline bg-paper px-4 py-3 text-sm text-ink">
                  <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-hairline pt-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        m.auditStatus === 'pass'
                          ? 'bg-positive-soft text-positive'
                          : 'bg-negative-soft text-negative'
                      }`}
                    >
                      {m.auditStatus === 'pass' ? 'Verified' : 'Unverified'}
                    </span>
                    {m.sources.map((s, j) => (
                      <span key={j} className="rounded-full bg-cream-soft px-2 py-0.5 text-xs text-ink-muted">
                        {TOOL_LABELS[s.tool] ?? s.tool}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
          {loading && (
            <div className="flex justify-start">
              <div className="rounded-2xl rounded-bl-sm border border-hairline bg-paper px-4 py-2 text-sm text-ink-muted">
                Thinking&hellip;
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && ask()}
          placeholder="e.g. How does Boeing's Reddit sentiment compare to its stock price?"
          disabled={loading}
          className="min-w-[200px] flex-1 rounded-xl border border-hairline bg-cream px-4 py-2.5 text-sm text-ink outline-none placeholder:text-ink-muted/70 focus:border-accent focus:ring-2 focus:ring-accent-soft disabled:opacity-50"
        />
        <button
          onClick={ask}
          disabled={!question.trim() || loading}
          className="rounded-xl bg-accent px-5 py-2.5 text-sm font-semibold text-cream transition hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? 'Asking...' : 'Ask'}
        </button>
      </div>
    </div>
  );
}
