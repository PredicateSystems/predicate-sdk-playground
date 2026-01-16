'use client';

import { useEffect, useMemo, useState } from 'react';

type Item = { id: string; text: string };

export default function ActivityEmbed() {
  const delayMs = useMemo(() => 700 + Math.floor(Math.random() * 600), []);
  const [items, setItems] = useState<Item[] | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setItems([
        { id: 'a1', text: '✨ You earned +3 Llama Coins' },
        { id: 'a2', text: '🧭 You joined the “Show HN” herd' },
        { id: 'a3', text: '📌 You pinned “How to raise alpacas”' },
      ]);
    }, delayMs);
    return () => clearTimeout(t);
  }, [delayMs]);

  return (
    <div className="p-4 text-white">
      <div className="text-sm font-semibold">Activity</div>
      <div className="mt-1 text-xs text-white/60">Loads after {delayMs}ms</div>

      {!items ? (
        <div className="mt-4 text-sm text-white/70">Loading…</div>
      ) : (
        <ul className="mt-4 space-y-2">
          {items.map(i => (
            <li key={i.id} className="rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm">
              {i.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

