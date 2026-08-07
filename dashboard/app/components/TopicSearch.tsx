'use client';

import { useState } from 'react';
import { API_URL, apiFetch } from '../lib/api';

type Status = { kind: 'idle' } | { kind: 'queued'; query: string } | { kind: 'error'; message: string };

export default function TopicSearch() {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<Status>({ kind: 'idle' });

  async function submit() {
    const q = query.trim();
    if (!q) return;
    try {
      const res = await apiFetch(`${API_URL}/api/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q }),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      setStatus({ kind: 'queued', query: q });
      setQuery('');
    } catch (e) {
      setStatus({ kind: 'error', message: e instanceof Error ? e.message : 'Request failed' });
    }
  }

  return (
    <div className="rounded-2xl border border-hairline bg-paper p-6 shadow-[0_1px_2px_rgba(42,30,23,0.04),0_20px_40px_-24px_rgba(122,31,46,0.4)]">
      <h2 className="mb-1 font-serif text-2xl font-semibold text-ink">Research a topic</h2>
      <p className="mb-4 text-sm leading-relaxed text-ink-muted">
        Type anything &mdash; a company, an industry, a person. EchoSystem&ndash;AI will pull real
        news articles about it, extract entities and relationships into the graph, and generate a
        fact-checked summary report on the exact topic you searched.
      </p>
      <div className="flex flex-wrap gap-3">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          placeholder="e.g. Nvidia, EV battery supply chain, Anthropic..."
          className="min-w-[240px] flex-1 rounded-xl border border-hairline bg-cream px-4 py-2.5 text-sm text-ink outline-none placeholder:text-ink-muted/70 focus:border-accent focus:ring-2 focus:ring-accent-soft"
        />
        <button
          onClick={submit}
          disabled={!query.trim()}
          className="rounded-xl bg-accent px-5 py-2.5 text-sm font-semibold text-cream transition hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-40"
        >
          Research
        </button>
      </div>
      {status.kind === 'queued' && (
        <p className="mt-3 text-sm text-positive">
          Researching &ldquo;{status.query}&rdquo;&mdash;articles are being fetched and processed.
          Entities will appear in the graph below within about a minute; a summary report on this
          topic will follow shortly after in Latest Reports.
        </p>
      )}
      {status.kind === 'error' && (
        <p className="mt-3 text-sm text-negative">Couldn&apos;t start research: {status.message}</p>
      )}
    </div>
  );
}
