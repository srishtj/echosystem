import Link from 'next/link';
import ImpactStats from '../components/ImpactStats';

export default function ImpactPage() {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-12">
      <header>
        <Link href="/" className="text-sm font-medium text-accent hover:underline">
          &larr; Back to dashboard
        </Link>
        <p className="mb-1 mt-4 font-mono text-xs uppercase tracking-[0.2em] text-ink-muted">
          Critic Loop performance
        </p>
        <h1 className="font-serif text-4xl font-semibold tracking-tight text-ink">Impact</h1>
        <p className="mt-1 text-sm text-ink-muted">
          How much work the Critic Loop is doing, and what it&apos;s catching.
        </p>
      </header>

      <ImpactStats />
    </div>
  );
}
