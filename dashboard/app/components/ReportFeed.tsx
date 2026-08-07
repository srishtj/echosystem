'use client';

import useSWR from 'swr';
import { API_URL, apiFetch } from '../lib/api';

const fetcher = (url: string) => apiFetch(url).then((r) => r.json());

type Report = {
  id: string;
  topic: string;
  final_report: string;
  audit_status: string;
  retry_count: number;
  created_at: number;
  related_entities: string[];
};

const STATUS_STYLES: Record<string, string> = {
  pass: 'bg-positive-soft text-positive',
  fail: 'bg-negative-soft text-negative',
};

export default function ReportFeed({
  onShowInGraph,
  onSelectEntity,
}: {
  onShowInGraph?: (entities: string[]) => void;
  onSelectEntity?: (name: string) => void;
}) {
  const { data, error } = useSWR<Report[]>(`${API_URL}/api/reports`, fetcher, {
    refreshInterval: 20000,
  });

  if (error) return <p className="text-sm text-negative">Failed to load reports.</p>;
  if (!data) return <p className="text-sm text-ink-muted">Loading reports...</p>;
  if (data.length === 0)
    return (
      <p className="text-sm text-ink-muted">No reports yet &mdash; the Critic Loop hasn&apos;t run.</p>
    );

  return (
    <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
      {data.map((r) => (
        <div
          key={r.id}
          className="rounded-2xl border border-hairline bg-paper p-5 shadow-[0_1px_2px_rgba(42,30,23,0.04),0_16px_32px_-20px_rgba(122,31,46,0.35)]"
        >
          <div className="flex items-start justify-between gap-3">
            <h3 className="font-serif text-lg font-semibold leading-snug text-ink">{r.topic}</h3>
            {r.related_entities.length > 0 && (
              <button
                onClick={() => onShowInGraph?.(r.related_entities)}
                className="shrink-0 rounded-full border border-accent/40 px-2.5 py-1 text-xs font-medium text-accent hover:bg-accent-soft"
              >
                Show in graph
              </button>
            )}
          </div>
          <div className="mt-1.5 flex items-center gap-2 text-xs text-ink-muted">
            <span
              className={`rounded-full px-2 py-0.5 font-medium ${STATUS_STYLES[r.audit_status] ?? 'bg-cream-soft text-ink-muted'}`}
            >
              {r.audit_status}
            </span>
            <span>Audit retries: {r.retry_count}</span>
          </div>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-ink">{r.final_report}</p>
          {r.related_entities.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {r.related_entities.map((entity) => (
                <button
                  key={entity}
                  onClick={() => onSelectEntity?.(entity)}
                  className="rounded-full bg-cream-soft px-2.5 py-0.5 text-xs text-ink-muted hover:bg-accent-soft hover:text-accent"
                >
                  {entity}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
