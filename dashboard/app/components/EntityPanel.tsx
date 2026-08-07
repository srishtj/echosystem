'use client';

import useSWR from 'swr';
import MarketData from './MarketData';
import { API_URL, apiFetch } from '../lib/api';

const fetcher = (url: string) => apiFetch(url).then((r) => r.json());

type Relation = { relation: string; neighbor: string; direction: 'in' | 'out'; evidence: string | null };
type Claim = {
  claim: string;
  source: string | null;
  published_at: string | null;
  contradiction_count: number;
};
type EntityDetail = { name: string; type: string; relations: Relation[]; claims: Claim[] };

function formatDate(iso: string | null): string {
  if (!iso) return 'Undated';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return 'Undated';
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function hostnameOf(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return null;
  }
}

const TYPE_COLORS: Record<string, string> = {
  Company: '#7a1f2e',
  Person: '#a9793a',
  Material: '#3f6b4a',
  Product: '#4a5a73',
};

export default function EntityPanel({ name, onClose }: { name: string; onClose: () => void }) {
  const { data, error } = useSWR<EntityDetail>(
    `${API_URL}/api/entity/${encodeURIComponent(name)}`,
    fetcher
  );

  return (
    <div className="rounded-2xl border border-hairline bg-paper p-5 shadow-[0_1px_2px_rgba(42,30,23,0.04),0_16px_32px_-20px_rgba(122,31,46,0.35)]">
      <div className="mb-3 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            {data && (
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: TYPE_COLORS[data.type] ?? '#9c8b76' }}
              />
            )}
            <h3 className="font-serif text-lg font-semibold text-ink">{name}</h3>
          </div>
          {data && <p className="text-sm text-ink-muted">{data.type}</p>}
        </div>
        <button
          onClick={onClose}
          className="rounded-full px-2.5 py-1 text-sm text-ink-muted hover:bg-cream-soft hover:text-ink"
        >
          Close
        </button>
      </div>

      {error && <p className="text-sm text-negative">Failed to load entity details.</p>}
      {!error && !data && <p className="text-sm text-ink-muted">Loading...</p>}

      {data && (
        <div className="space-y-5">
          <div>
            <h4 className="mb-2 font-mono text-xs uppercase tracking-widest text-ink-muted">
              Relationships ({data.relations.length})
            </h4>
            {data.relations.length === 0 && (
              <p className="text-sm text-ink-muted">No relationships recorded.</p>
            )}
            <ul className="space-y-1.5">
              {data.relations.map((r, i) => (
                <li key={i} className="text-sm text-ink">
                  {r.direction === 'out' ? (
                    <span>
                      <span className="font-medium">{name}</span>{' '}
                      <span className="text-accent">{r.relation}</span>{' '}
                      <span className="font-medium">{r.neighbor}</span>
                    </span>
                  ) : (
                    <span>
                      <span className="font-medium">{r.neighbor}</span>{' '}
                      <span className="text-accent">{r.relation}</span>{' '}
                      <span className="font-medium">{name}</span>
                    </span>
                  )}
                  {r.evidence && (
                    <p className="pl-3 text-xs italic text-ink-muted">&ldquo;{r.evidence}&rdquo;</p>
                  )}
                </li>
              ))}
            </ul>
          </div>

          {data.claims.length > 0 && (
            <div>
              <h4 className="mb-2 font-mono text-xs uppercase tracking-widest text-ink-muted">
                Timeline
              </h4>
              <ol className="space-y-3 border-l border-hairline pl-4">
                {data.claims.map((c, i) => (
                  <li key={i} className="relative text-sm">
                    <span className="absolute -left-[19px] top-1 h-2 w-2 rounded-full bg-accent" />
                    <div className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
                      <span>{formatDate(c.published_at)}</span>
                      {hostnameOf(c.source) && (
                        <>
                          <span>&middot;</span>
                          {c.source ? (
                            <a
                              href={c.source}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-accent hover:underline"
                            >
                              {hostnameOf(c.source)}
                            </a>
                          ) : (
                            <span>{hostnameOf(c.source)}</span>
                          )}
                        </>
                      )}
                      {c.contradiction_count > 0 && (
                        <span className="rounded-full bg-negative-soft px-2 py-0.5 text-negative">
                          {c.contradiction_count} contradiction(s)
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-ink">{c.claim}</p>
                  </li>
                ))}
              </ol>
            </div>
          )}

          <MarketData query={name} />
        </div>
      )}
    </div>
  );
}
