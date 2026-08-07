'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { API_URL, apiFetch } from '../lib/api';

const fetcher = (url: string) => apiFetch(url).then((r) => r.json());

type WatchlistEntry = {
  id: string;
  type: 'company' | 'topic';
  value: string;
  cadence: 'daily' | 'weekly';
  created_at: number;
  active: boolean;
  last_run_at: number | null;
};

export default function WatchlistManager() {
  const { data, error, mutate } = useSWR<WatchlistEntry[]>(`${API_URL}/api/watchlist`, fetcher, {
    refreshInterval: 30000,
  });

  const [type, setType] = useState<'company' | 'topic'>('company');
  const [value, setValue] = useState('');
  const [cadence, setCadence] = useState<'daily' | 'weekly'>('daily');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function addEntry() {
    const v = value.trim();
    if (!v) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const res = await apiFetch(`${API_URL}/api/watchlist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, value: v, cadence }),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      setValue('');
      mutate();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setSubmitting(false);
    }
  }

  async function removeEntry(id: string) {
    await apiFetch(`${API_URL}/api/watchlist/${id}`, { method: 'DELETE' });
    mutate();
  }

  function formatLastRun(ts: number | null): string {
    if (!ts) return 'never run yet';
    return `last researched ${new Date(ts * 1000).toLocaleString()}`;
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-hairline bg-paper p-6 shadow-[0_1px_2px_rgba(42,30,23,0.04),0_20px_40px_-24px_rgba(122,31,46,0.4)]">
        <h2 className="mb-1 font-serif text-2xl font-semibold text-ink">Add to watchlist</h2>
        <p className="mb-4 text-sm leading-relaxed text-ink-muted">
          Companies and topics on this list get researched automatically on the cadence you pick,
          and roll up into the daily digest &mdash; no code changes needed.
        </p>
        <div className="flex flex-wrap gap-3">
          <select
            value={type}
            onChange={(e) => setType(e.target.value as 'company' | 'topic')}
            className="rounded-xl border border-hairline bg-cream px-3 py-2.5 text-sm text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent-soft"
          >
            <option value="company">Company</option>
            <option value="topic">Topic</option>
          </select>
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addEntry()}
            placeholder="e.g. Nvidia, EV battery supply chain..."
            className="min-w-[200px] flex-1 rounded-xl border border-hairline bg-cream px-4 py-2.5 text-sm text-ink outline-none placeholder:text-ink-muted/70 focus:border-accent focus:ring-2 focus:ring-accent-soft"
          />
          <select
            value={cadence}
            onChange={(e) => setCadence(e.target.value as 'daily' | 'weekly')}
            className="rounded-xl border border-hairline bg-cream px-3 py-2.5 text-sm text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent-soft"
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
          </select>
          <button
            onClick={addEntry}
            disabled={!value.trim() || submitting}
            className="rounded-xl bg-accent px-5 py-2.5 text-sm font-semibold text-cream transition hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-40"
          >
            Add
          </button>
        </div>
        {formError && (
          <p className="mt-3 text-sm text-negative">Couldn&apos;t add entry: {formError}</p>
        )}
      </div>

      <div>
        <h2 className="mb-3 font-serif text-xl font-semibold text-ink">Watching</h2>
        {error && <p className="text-sm text-negative">Failed to load watchlist.</p>}
        {!error && !data && <p className="text-sm text-ink-muted">Loading watchlist...</p>}
        {data && data.length === 0 && (
          <p className="text-sm text-ink-muted">
            Nothing on the watchlist yet &mdash; add a company or topic above.
          </p>
        )}
        {data && data.length > 0 && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {data.map((entry) => (
              <div
                key={entry.id}
                className="flex items-center justify-between rounded-2xl border border-hairline bg-paper p-4 shadow-[0_1px_2px_rgba(42,30,23,0.04),0_12px_24px_-18px_rgba(122,31,46,0.3)]"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-ink">{entry.value}</span>
                    <span className="rounded-full bg-cream-soft px-2 py-0.5 text-xs text-ink-muted">
                      {entry.type}
                    </span>
                    <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs text-accent">
                      {entry.cadence}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-ink-muted">{formatLastRun(entry.last_run_at)}</p>
                </div>
                <button
                  onClick={() => removeEntry(entry.id)}
                  className="rounded-full border border-negative/30 px-3 py-1.5 text-xs font-medium text-negative hover:bg-negative-soft"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
