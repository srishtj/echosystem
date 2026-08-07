'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { API_URL, apiFetch } from '../lib/api';

const fetcher = (url: string) => apiFetch(url).then((r) => r.json());

const MAX_ENTITIES = 4;
const ENTITY_COLORS = ['#7a1f2e', '#a9793a', '#3f6b4a', '#4a5a73'];

type StockData = {
  symbol: string;
  current_price: number | null;
  change_percent: number | null;
  market_cap: number | null;
  prices: { date: string; close: number }[];
};

type SecFact = { value: number; end: string; form: string };

type CompareEntity = {
  name: string;
  mention_volume: number;
  sentiment_trend: { week: string; avg_sentiment: number }[];
  stock: StockData | null;
  sec_facts: Record<string, SecFact> | null;
};

const FACT_LABELS: Record<string, string> = {
  Revenues: 'Revenue',
  RevenueFromContractWithCustomerExcludingAssessedTax: 'Revenue',
  NetIncomeLoss: 'Net Income',
};

function compactCurrency(value: number | null | undefined): string {
  if (value == null) return '—';
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: 'USD',
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);
}

function sentimentLabel(score: number | undefined): { text: string; className: string } {
  if (score == null) return { text: 'No data', className: 'bg-cream-soft text-ink-muted' };
  if (score > 0.15) return { text: 'Positive', className: 'bg-positive-soft text-positive' };
  if (score < -0.15) return { text: 'Negative', className: 'bg-negative-soft text-negative' };
  return { text: 'Neutral', className: 'bg-cream-soft text-ink-muted' };
}

function buildChartData(entities: CompareEntity[]) {
  const dates = new Set<string>();
  const priceByDate: Record<string, Record<string, number>> = {};
  const sentimentByDate: Record<string, Record<string, number>> = {};

  entities.forEach((e) => {
    const prices = e.stock?.prices ?? [];
    const base = prices[0]?.close;
    prices.forEach((p) => {
      dates.add(p.date);
      priceByDate[p.date] ??= {};
      if (base) priceByDate[p.date][e.name] = (p.close / base) * 100;
    });
    e.sentiment_trend.forEach((s) => {
      dates.add(s.week);
      sentimentByDate[s.week] ??= {};
      sentimentByDate[s.week][e.name] = s.avg_sentiment;
    });
  });

  return Array.from(dates)
    .sort()
    .map((date) => {
      const row: Record<string, string | number | null> = { date };
      entities.forEach((e) => {
        row[`${e.name}__price`] = priceByDate[date]?.[e.name] ?? null;
        row[`${e.name}__sentiment`] = sentimentByDate[date]?.[e.name] ?? null;
      });
      return row;
    });
}

export default function CompareView() {
  const [entities, setEntities] = useState<string[]>([]);
  const [input, setInput] = useState('');

  function addEntity() {
    const v = input.trim();
    if (!v || entities.length >= MAX_ENTITIES || entities.includes(v)) return;
    setEntities([...entities, v]);
    setInput('');
  }

  function removeEntity(name: string) {
    setEntities(entities.filter((e) => e !== name));
  }

  const query = entities.join(',');
  const { data, error, isLoading } = useSWR<{ entities: CompareEntity[] }>(
    query ? `${API_URL}/api/compare?entities=${encodeURIComponent(query)}` : null,
    fetcher
  );

  const chartData = useMemo(() => buildChartData(data?.entities ?? []), [data]);
  const hasChartData = chartData.length > 0;

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-hairline bg-paper p-6 shadow-[0_1px_2px_rgba(42,30,23,0.04),0_20px_40px_-24px_rgba(122,31,46,0.4)]">
        <h2 className="mb-1 font-serif text-2xl font-semibold text-ink">Compare entities</h2>
        <p className="mb-4 text-sm leading-relaxed text-ink-muted">
          Add up to {MAX_ENTITIES} companies to see stock price, SEC fundamentals, mention
          volume, and sentiment trend side by side.
        </p>
        <div className="flex flex-wrap gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addEntity()}
            placeholder="e.g. Nvidia"
            disabled={entities.length >= MAX_ENTITIES}
            className="min-w-[200px] flex-1 rounded-xl border border-hairline bg-cream px-4 py-2.5 text-sm text-ink outline-none placeholder:text-ink-muted/70 focus:border-accent focus:ring-2 focus:ring-accent-soft disabled:opacity-50"
          />
          <button
            onClick={addEntity}
            disabled={!input.trim() || entities.length >= MAX_ENTITIES}
            className="rounded-xl bg-accent px-5 py-2.5 text-sm font-semibold text-cream transition hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-40"
          >
            Add
          </button>
        </div>
        {entities.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {entities.map((name, i) => (
              <span
                key={name}
                className="flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium"
                style={{ backgroundColor: `${ENTITY_COLORS[i]}1a`, color: ENTITY_COLORS[i] }}
              >
                {name}
                <button onClick={() => removeEntity(name)} className="hover:opacity-60">
                  &times;
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {error && <p className="text-sm text-negative">Failed to load comparison.</p>}
      {isLoading && <p className="text-sm text-ink-muted">Loading comparison...</p>}

      {data && data.entities.length > 0 && (
        <>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
            {data.entities.map((e, i) => {
              const latestSentiment = e.sentiment_trend.at(-1)?.avg_sentiment;
              const sentiment = sentimentLabel(latestSentiment);
              const changeUp = (e.stock?.change_percent ?? 0) >= 0;
              const facts = e.sec_facts
                ? Object.entries(e.sec_facts).filter(
                    ([key]) =>
                      key !== 'RevenueFromContractWithCustomerExcludingAssessedTax' ||
                      !e.sec_facts?.Revenues
                  )
                : [];

              return (
                <div
                  key={e.name}
                  className="rounded-2xl border border-hairline bg-paper p-5 shadow-[0_1px_2px_rgba(42,30,23,0.04),0_16px_32px_-20px_rgba(122,31,46,0.35)]"
                >
                  <div className="mb-3 flex items-center gap-2">
                    <span
                      className="inline-block h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: ENTITY_COLORS[i] }}
                    />
                    <h3 className="font-serif text-lg font-semibold text-ink">{e.name}</h3>
                  </div>

                  {e.stock ? (
                    <div className="mb-3 text-sm">
                      <div className="font-mono text-xs uppercase tracking-widest text-ink-muted">
                        {e.stock.symbol}
                      </div>
                      <div className="mt-1">
                        <span className="font-medium text-ink">{e.stock.current_price ?? '—'}</span>{' '}
                        {e.stock.change_percent != null && (
                          <span className={changeUp ? 'text-positive' : 'text-negative'}>
                            ({changeUp ? '+' : ''}
                            {e.stock.change_percent.toFixed(2)}%)
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-ink-muted">
                        Market cap {compactCurrency(e.stock.market_cap)}
                      </div>
                    </div>
                  ) : (
                    <p className="mb-3 text-xs text-ink-muted">No stock data found.</p>
                  )}

                  {facts.length > 0 && (
                    <div className="mb-3 space-y-0.5 text-xs">
                      {facts.map(([key, fact]) => (
                        <div key={key}>
                          <span className="text-ink-muted">{FACT_LABELS[key] ?? key} </span>
                          <span className="font-medium text-ink">{compactCurrency(fact.value)}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="flex items-center justify-between border-t border-hairline pt-3 text-xs">
                    <span className="text-ink-muted">{e.mention_volume} mention(s)</span>
                    <span className={`rounded-full px-2 py-0.5 font-medium ${sentiment.className}`}>
                      {sentiment.text}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {hasChartData && (
            <div className="rounded-2xl border border-hairline bg-paper p-5 shadow-[0_1px_2px_rgba(42,30,23,0.04),0_16px_32px_-20px_rgba(122,31,46,0.35)]">
              <h3 className="mb-1 font-mono text-xs uppercase tracking-widest text-ink-muted">
                Normalized price (solid) &amp; sentiment trend (dashed)
              </h3>
              <div className="h-80 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid stroke="#e2d3b3" strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#7c6a58' }} minTickGap={30} />
                    <YAxis
                      yAxisId="price"
                      domain={['auto', 'auto']}
                      tick={{ fontSize: 11, fill: '#7c6a58' }}
                      label={{ value: 'Index (100 = start)', angle: -90, position: 'insideLeft', fontSize: 11, fill: '#7c6a58' }}
                    />
                    <YAxis
                      yAxisId="sentiment"
                      orientation="right"
                      domain={[-1, 1]}
                      tick={{ fontSize: 11, fill: '#7c6a58' }}
                      label={{ value: 'Sentiment', angle: 90, position: 'insideRight', fontSize: 11, fill: '#7c6a58' }}
                    />
                    <Tooltip
                      contentStyle={{
                        background: '#2a1e17',
                        border: '1px solid #551420',
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                      labelStyle={{ color: '#f5ecdb' }}
                      itemStyle={{ color: '#f5ecdb' }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    {data.entities.map((e, i) => (
                      <Line
                        key={`${e.name}-price`}
                        yAxisId="price"
                        type="monotone"
                        dataKey={`${e.name}__price`}
                        name={`${e.name} price`}
                        stroke={ENTITY_COLORS[i]}
                        strokeWidth={2}
                        dot={false}
                        connectNulls
                      />
                    ))}
                    {data.entities.map((e, i) => (
                      <Line
                        key={`${e.name}-sentiment`}
                        yAxisId="sentiment"
                        type="monotone"
                        dataKey={`${e.name}__sentiment`}
                        name={`${e.name} sentiment`}
                        stroke={ENTITY_COLORS[i]}
                        strokeWidth={1.5}
                        strokeDasharray="4 4"
                        dot={{ r: 3 }}
                        connectNulls
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </>
      )}

      {data && data.entities.length === 0 && (
        <p className="text-sm text-ink-muted">No comparison data yet.</p>
      )}
    </div>
  );
}
