'use client';

import useSWR from 'swr';
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { API_URL, apiFetch } from '../lib/api';

const MANUAL_BASELINE_MINUTES = process.env.NEXT_PUBLIC_MANUAL_BASELINE_MINUTES
  ? Number(process.env.NEXT_PUBLIC_MANUAL_BASELINE_MINUTES)
  : null;

const fetcher = (url: string) => apiFetch(url).then((r) => r.json());

type Stats = {
  total_reports: number;
  avg_duration_seconds: number | null;
  total_claims_flagged: number;
  audit_catch_rate: number;
  audit_recovery_rate: number | null;
  total_estimated_cost_usd: number;
  total_contradictions: number;
  reports_per_day: { date: string; count: number }[];
};

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—';
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}m ${rest}s`;
}

function formatPercent(fraction: number | null): string {
  if (fraction == null) return '—';
  return `${(fraction * 100).toFixed(0)}%`;
}

function StatCard({
  label,
  value,
  sublabel,
  span = 1,
}: {
  label: string;
  value: string;
  sublabel?: string;
  span?: 1 | 2;
}) {
  return (
    <div
      className={`rounded-2xl border border-hairline bg-paper p-5 shadow-[0_1px_2px_rgba(42,30,23,0.04),0_16px_32px_-20px_rgba(122,31,46,0.35)] ${span === 2 ? 'col-span-2' : 'col-span-1'}`}
    >
      <div className="font-mono text-xs uppercase tracking-widest text-ink-muted">{label}</div>
      <div className="mt-2 font-serif text-3xl font-semibold text-ink">{value}</div>
      {sublabel && <div className="mt-1.5 text-xs leading-relaxed text-ink-muted">{sublabel}</div>}
    </div>
  );
}

export default function ImpactStats() {
  const { data, error } = useSWR<Stats>(`${API_URL}/api/stats`, fetcher, {
    refreshInterval: 30000,
  });

  if (error) return <p className="text-sm text-negative">Failed to load stats.</p>;
  if (!data) return <p className="text-sm text-ink-muted">Loading stats...</p>;

  const avgMinutes = data.avg_duration_seconds != null ? data.avg_duration_seconds / 60 : null;
  const timeSavedPct =
    avgMinutes != null && MANUAL_BASELINE_MINUTES
      ? Math.max(0, (1 - avgMinutes / MANUAL_BASELINE_MINUTES) * 100)
      : null;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Reports Generated" value={String(data.total_reports)} />
        <StatCard
          label="Audit Catch Rate"
          value={formatPercent(data.audit_catch_rate)}
          sublabel={`${data.total_claims_flagged} claim(s) flagged`}
        />
        <StatCard
          label="Audit Recovery Rate"
          value={formatPercent(data.audit_recovery_rate)}
          sublabel="Passed on retry"
        />
        <StatCard label="Contradictions Surfaced" value={String(data.total_contradictions)} />
        <StatCard
          label="Avg Generation Time"
          value={formatDuration(data.avg_duration_seconds)}
          sublabel={
            timeSavedPct != null
              ? `${timeSavedPct.toFixed(0)}% faster than your ${MANUAL_BASELINE_MINUTES}m manual baseline`
              : 'Set NEXT_PUBLIC_MANUAL_BASELINE_MINUTES to compare against a manual baseline'
          }
          span={2}
        />
        <StatCard
          label="Est. Cost (paid tier)"
          value={`$${data.total_estimated_cost_usd.toFixed(4)}`}
          sublabel="What this usage would cost off the Groq free tier"
          span={2}
        />
      </div>

      {data.reports_per_day.length > 0 && (
        <div className="rounded-2xl border border-hairline bg-paper p-5 shadow-[0_1px_2px_rgba(42,30,23,0.04),0_16px_32px_-20px_rgba(122,31,46,0.35)]">
          <h3 className="mb-3 font-mono text-xs uppercase tracking-widest text-ink-muted">
            Reports per day (last 30 days)
          </h3>
          <div className="h-48 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.reports_per_day}>
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#7c6a58' }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#7c6a58' }} />
                <Tooltip
                  contentStyle={{
                    background: '#2a1e17',
                    border: '1px solid #551420',
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  labelStyle={{ color: '#f5ecdb' }}
                  itemStyle={{ color: '#f5ecdb' }}
                  cursor={{ fill: 'rgba(122, 31, 46, 0.08)' }}
                />
                <Bar dataKey="count" fill="#7a1f2e" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
