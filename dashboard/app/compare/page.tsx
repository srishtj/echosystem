import Link from 'next/link';
import CompareView from '../components/CompareView';

export default function ComparePage() {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-12">
      <header>
        <Link href="/" className="text-sm font-medium text-accent hover:underline">
          &larr; Back to dashboard
        </Link>
        <p className="mb-1 mt-4 font-mono text-xs uppercase tracking-[0.2em] text-ink-muted">
          Side-by-side research
        </p>
        <h1 className="font-serif text-4xl font-semibold tracking-tight text-ink">Compare</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Stock price, fundamentals, and sentiment trend across companies you&apos;re researching.
        </p>
      </header>

      <CompareView />
    </div>
  );
}
