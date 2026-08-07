'use client';

import useSWR from 'swr';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { API_URL, apiFetch } from '../lib/api';

const fetcher = async (url: string) => {
  const res = await apiFetch(url);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Server returned ${res.status}`);
  return res.json();
};

type StockData = {
  symbol: string;
  name: string;
  exchange: string | null;
  current_price: number | null;
  change_percent: number | null;
  market_cap: number | null;
  fifty_two_week_high: number | null;
  fifty_two_week_low: number | null;
  sector: string | null;
  prices: { date: string; close: number }[];
};

type SecFact = { value: number; end: string; form: string };
type SecData = {
  cik: number;
  title: string;
  ticker: string;
  facts: Record<string, SecFact>;
  filings: { company: string; form: string; filed: string; url: string | null }[];
};

type RedditPost = {
  title: string;
  subreddit: string;
  score: number;
  num_comments: number;
  created_at: string;
  url: string;
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

const FACT_LABELS: Record<string, string> = {
  Revenues: 'Revenue',
  RevenueFromContractWithCustomerExcludingAssessedTax: 'Revenue',
  NetIncomeLoss: 'Net Income',
  Assets: 'Total Assets',
  Liabilities: 'Total Liabilities',
};

function StockSection({ query }: { query: string }) {
  const { data, error } = useSWR<StockData | null>(
    `${API_URL}/api/stock/${encodeURIComponent(query)}`,
    fetcher
  );

  if (error) return null;
  if (!data) return null;

  const changeUp = (data.change_percent ?? 0) >= 0;

  return (
    <div>
      <h4 className="mb-2 font-mono text-xs uppercase tracking-widest text-ink-muted">
        Stock &mdash; {data.symbol} ({data.exchange})
      </h4>
      <div className="mb-3 flex flex-wrap gap-4 text-sm">
        <div>
          <span className="text-ink-muted">Price </span>
          <span className="font-medium text-ink">{data.current_price ?? '—'}</span>{' '}
          {data.change_percent != null && (
            <span className={changeUp ? 'text-positive' : 'text-negative'}>
              ({changeUp ? '+' : ''}
              {data.change_percent.toFixed(2)}%)
            </span>
          )}
        </div>
        <div>
          <span className="text-ink-muted">Market Cap </span>
          <span className="font-medium text-ink">{compactCurrency(data.market_cap)}</span>
        </div>
        <div>
          <span className="text-ink-muted">52wk Range </span>
          <span className="font-medium text-ink">
            {data.fifty_two_week_low} &ndash; {data.fifty_two_week_high}
          </span>
        </div>
      </div>
      <div className="h-40 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data.prices}>
            <XAxis dataKey="date" hide />
            <YAxis domain={['auto', 'auto']} hide />
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
            <Line type="monotone" dataKey="close" stroke="#7a1f2e" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function SecSection({ query }: { query: string }) {
  const { data, error } = useSWR<SecData | null>(
    `${API_URL}/api/sec/${encodeURIComponent(query)}`,
    fetcher
  );

  if (error) return null;
  if (!data) return null;

  const factEntries = Object.entries(data.facts).filter(
    ([key]) => key !== 'RevenueFromContractWithCustomerExcludingAssessedTax' || !data.facts.Revenues
  );

  return (
    <div>
      <h4 className="mb-2 font-mono text-xs uppercase tracking-widest text-ink-muted">
        SEC Filings &mdash; {data.title} ({data.ticker})
      </h4>
      {factEntries.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-4 text-sm">
          {factEntries.map(([key, fact]) => (
            <div key={key}>
              <span className="text-ink-muted">{FACT_LABELS[key] ?? key} </span>
              <span className="font-medium text-ink">{compactCurrency(fact.value)}</span>{' '}
              <span className="text-xs text-ink-muted">({fact.end})</span>
            </div>
          ))}
        </div>
      )}
      <ul className="space-y-1 text-sm">
        {data.filings.slice(0, 5).map((f, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className="rounded-full bg-accent-soft px-1.5 py-0.5 text-xs text-accent">
              {f.form}
            </span>
            <span className="text-ink-muted">{f.filed}</span>
            {f.url && (
              <a
                href={f.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent hover:underline"
              >
                View filing
              </a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function RedditSection({ query }: { query: string }) {
  const { data, error } = useSWR<RedditPost[] | null>(
    `${API_URL}/api/social/${encodeURIComponent(query)}`,
    fetcher
  );

  if (error) return null;
  if (!data || data.length === 0) return null;

  return (
    <div>
      <h4 className="mb-2 font-mono text-xs uppercase tracking-widest text-ink-muted">
        Reddit mentions
      </h4>
      <ul className="space-y-2 text-sm">
        {data.slice(0, 6).map((p, i) => (
          <li key={i}>
            <a
              href={p.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline"
            >
              {p.title}
            </a>
            <div className="text-xs text-ink-muted">
              r/{p.subreddit} &middot; {p.score} upvotes &middot; {p.num_comments} comments
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function MarketData({ query }: { query: string }) {
  return (
    <div className="space-y-5 border-t border-hairline pt-5">
      <StockSection query={query} />
      <SecSection query={query} />
      <RedditSection query={query} />
    </div>
  );
}
