'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { HydrationGate } from './hydration-gate';
import { Button } from '../ui/button';

type Item = { id: string; title: string };

function makeItems(prefix: string, start: number, n: number): Item[] {
  const out: Item[] = [];
  for (let i = 0; i < n; i++) {
    const k = start + i;
    out.push({ id: `${prefix}-${k}`, title: `${prefix} Result ${k}: Example title` });
  }
  return out;
}

/**
 * A deterministic fixture for testing Phase 2 "Reveal" behavior:
 * - delayed hydration
 * - scrollable container with list items
 * - "Load more results" button that appends more items after a delay
 * - pagination-like navigation via `?page=2`
 */
export function RevealFixtureClient() {
  const page = useMemo(() => {
    if (typeof window === 'undefined') return 1;
    const params = new URLSearchParams(window.location.search);
    const p = Number(params.get('page') || '1');
    return Number.isFinite(p) && p >= 1 ? p : 1;
  }, []);

  const [items, setItems] = useState<Item[]>([]);
  const [loadedPages, setLoadedPages] = useState(1);
  const [loadingMore, setLoadingMore] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const prefix = page === 2 ? 'Page2' : 'Page1';

  useEffect(() => {
    // Initial content after hydration.
    setItems(makeItems(prefix, 1, 6));
    setLoadedPages(1);
    setLoadingMore(false);
  }, [prefix]);

  const canLoadMore = loadedPages < 2;

  const onLoadMore = () => {
    if (!canLoadMore || loadingMore) return;
    setLoadingMore(true);
    // Delayed append to simulate async fetch/render.
    setTimeout(() => {
      setItems(prev => [...prev, ...makeItems(prefix, 7, 6)]);
      setLoadedPages(2);
      setLoadingMore(false);
    }, 550);
  };

  return (
    <HydrationGate label="Hydrating reveal fixture…" baseDelayMs={600} jitterMs={600}>
      <div className="glass rounded-xl p-6 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-sm font-semibold">Reveal fixture</div>
            <div className="text-xs text-white/60">
              Scroll container + Load more + Pagination link. Current page: {page}.
            </div>
          </div>
          <div className="flex gap-2">
            {page === 1 ? (
              <Link href="/fixtures/reveal?page=2">
                <Button variant="secondary">Next page</Button>
              </Link>
            ) : (
              <Link href="/fixtures/reveal?page=1">
                <Button variant="secondary">Previous page</Button>
              </Link>
            )}
          </div>
        </div>

        <div className="rounded-lg border border-white/10 bg-black/30 p-4">
          <button
            type="button"
            className="text-sm font-medium underline decoration-white/20 underline-offset-4"
            aria-expanded={filtersOpen ? 'true' : 'false'}
            onClick={() => setFiltersOpen(v => !v)}
          >
            Filters
          </button>
          {filtersOpen ? (
            <div className="mt-3 text-xs text-white/70">
              (Pretend filters go here. This accordion is only for testing expand/reveal logic.)
            </div>
          ) : (
            <div className="mt-3 text-xs text-white/50">(collapsed)</div>
          )}
        </div>

        <div
          className="rounded-lg border border-white/10 bg-black/30 p-4"
          style={{ maxHeight: 260, overflowY: 'auto' }}
          data-testid="reveal-scroll-container"
        >
          <div className="text-xs text-white/60">Results</div>
          <ul className="mt-3 space-y-2">
            {items.map(it => (
              <li key={it.id} className="rounded-md border border-white/10 bg-white/5 p-3">
                <div className="text-sm font-medium">{it.title}</div>
                <div className="text-xs text-white/60">Type: Article</div>
              </li>
            ))}
          </ul>
        </div>

        <div className="flex items-center justify-between">
          <div className="text-xs text-white/60">
            Loaded: {items.length} items {loadingMore ? '(loading…)': ''}
          </div>
          {canLoadMore ? (
            <Button onClick={onLoadMore} disabled={loadingMore}>
              {loadingMore ? 'Loading…' : 'Load more results'}
            </Button>
          ) : (
            <div className="text-xs text-white/60">(no more)</div>
          )}
        </div>
      </div>
    </HydrationGate>
  );
}

