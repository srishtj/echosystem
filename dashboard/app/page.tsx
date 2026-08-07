'use client';

import { useState } from 'react';
import Link from 'next/link';
import GraphView from './components/GraphView';
import ReportFeed from './components/ReportFeed';
import EntityPanel from './components/EntityPanel';
import TopicSearch from './components/TopicSearch';
import AskAgent from './components/AskAgent';

export default function Home() {
  const [highlightEntities, setHighlightEntities] = useState<string[] | undefined>(undefined);
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);

  function selectEntity(name: string) {
    setSelectedEntity(name);
    setHighlightEntities([name]);
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-12">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-1 font-mono text-xs uppercase tracking-[0.2em] text-ink-muted">
            Market intelligence, fact-checked
          </p>
          <h1 className="font-serif text-4xl font-semibold tracking-tight text-ink">
            EchoSystem&ndash;AI
          </h1>
        </div>
        <nav className="flex gap-2">
          <Link
            href="/compare"
            className="rounded-full border border-hairline bg-paper px-4 py-2 text-sm font-medium text-ink transition hover:border-accent hover:text-accent"
          >
            Compare
          </Link>
          <Link
            href="/settings"
            className="rounded-full border border-hairline bg-paper px-4 py-2 text-sm font-medium text-ink transition hover:border-accent hover:text-accent"
          >
            Settings
          </Link>
          <Link
            href="/impact"
            className="rounded-full border border-hairline bg-paper px-4 py-2 text-sm font-medium text-ink transition hover:border-accent hover:text-accent"
          >
            Impact
          </Link>
        </nav>
      </header>

      <section>
        <TopicSearch />
      </section>

      <section>
        <AskAgent />
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="rounded-2xl border border-hairline bg-paper p-5 shadow-[0_1px_2px_rgba(42,30,23,0.04),0_16px_32px_-20px_rgba(122,31,46,0.35)] lg:col-span-2">
          <h2 className="mb-3 font-serif text-xl font-semibold text-ink">Knowledge Graph</h2>
          <GraphView highlightEntities={highlightEntities} onNodeClick={selectEntity} />
        </div>

        <div className="lg:col-span-1">
          {selectedEntity ? (
            <EntityPanel name={selectedEntity} onClose={() => setSelectedEntity(null)} />
          ) : (
            <div className="rounded-2xl border border-hairline bg-paper p-5 shadow-[0_1px_2px_rgba(42,30,23,0.04),0_16px_32px_-20px_rgba(122,31,46,0.35)]">
              <h3 className="mb-2 font-serif text-lg font-semibold text-ink">How to read this</h3>
              <p className="text-sm leading-relaxed text-ink-muted">
                Every dot is a company, person, material, or product mentioned in a real news
                article; every line is a relationship (e.g. &ldquo;acquired&rdquo;,
                &ldquo;competes with&rdquo;) pulled from that article&apos;s text. Nothing shows
                up until you research a topic above &mdash; the graph only knows what it&apos;s
                actually read.
              </p>
              <p className="mt-3 text-sm leading-relaxed text-ink-muted">
                Hover a node for a quick summary, click it for full sourced details here.
              </p>
              <div className="mt-4 border-t border-hairline pt-4">
                <p className="mb-2 font-mono text-xs uppercase tracking-widest text-ink-muted">
                  Node types
                </p>
                <div className="flex flex-wrap gap-3 text-xs text-ink-muted">
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block h-2.5 w-2.5 rounded-full bg-accent" /> Company
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block h-2.5 w-2.5 rounded-full bg-gold" /> Person
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block h-2.5 w-2.5 rounded-full bg-positive" /> Material
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#4a5a73]" /> Product
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      <section>
        <h2 className="mb-3 font-serif text-xl font-semibold text-ink">Latest Reports</h2>
        <ReportFeed
          onShowInGraph={(entities) => setHighlightEntities(entities)}
          onSelectEntity={selectEntity}
        />
      </section>
    </div>
  );
}
