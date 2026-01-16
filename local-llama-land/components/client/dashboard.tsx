'use client';

import { useEffect, useMemo, useState } from 'react';
import { Button } from '../ui/button';

type KPI = { label: string; value: string; hint: string };
type Row = { id: string; event: string; ts: string; status: 'ok' | 'warn' };

export function DashboardClient() {
  const [ready, setReady] = useState(false);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [live, setLive] = useState(false);

  const delayMs = useMemo(() => 900 + Math.floor(Math.random() * 600), []);

  useEffect(() => {
    const t = setTimeout(() => {
      setReady(true);
      setRows([
        { id: 'r1', event: 'Signed in', ts: 'just now', status: 'ok' },
        { id: 'r2', event: 'Viewed profile', ts: '1m ago', status: 'ok' },
        { id: 'r3', event: 'Attempted form submit', ts: '3m ago', status: 'warn' },
      ]);
    }, delayMs);
    return () => clearTimeout(t);
  }, [delayMs]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    if (params.get('live') === '1') setLive(true);
  }, []);

  useEffect(() => {
    if (!live) return;
    const t = setInterval(() => {
      setRows(prev => {
        if (!prev) return prev;
        const next = [...prev];
        // structural churn: add/remove row
        const id = `r${Date.now()}`;
        next.unshift({
          id,
          event: 'Live ping',
          ts: new Date().toLocaleTimeString(),
          status: 'ok',
        });
        if (next.length > 6) next.pop();
        return next;
      });
    }, 400);
    return () => clearInterval(t);
  }, [live]);

  const kpis: KPI[] = [
    { label: 'Llama Coins', value: '128', hint: 'Monthly balance' },
    { label: 'Active Herds', value: '7', hint: 'Groups you follow' },
    { label: 'Messages', value: '3', hint: 'Unread' },
  ];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        {kpis.map(k => (
          <div key={k.label} className="glass rounded-xl p-5">
            <div className="text-xs text-white/60">{k.label}</div>
            <div className="mt-2 text-3xl font-semibold" data-testid={`kpi-${k.label}`}>
              {k.value}
            </div>
            <div className="mt-1 text-xs text-white/50">{k.hint}</div>
          </div>
        ))}
      </div>

      <div className="glass rounded-xl p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-sm font-semibold">Engagement</div>
            <div className="text-xs text-white/60">Chart placeholder (simple SVG)</div>
          </div>
          <Button variant="secondary" onClick={() => setLive(v => !v)}>
            {live ? 'Disable live updates' : 'Enable live updates'}
          </Button>
        </div>
        <div className="mt-4 rounded-lg border border-white/10 bg-black/30 p-4">
          <svg width="100%" height="120" viewBox="0 0 600 120" role="img" aria-label="chart">
            <polyline
              fill="none"
              stroke="white"
              strokeOpacity="0.6"
              strokeWidth="2"
              points="0,80 80,50 160,70 240,40 320,55 400,30 480,45 560,25 600,35"
            />
          </svg>
        </div>
      </div>

      <div className="glass rounded-xl p-6">
        <div className="text-sm font-semibold">Recent events</div>
        <div className="text-xs text-white/60">Loads after {delayMs}ms</div>

        {!ready || !rows ? (
          <div className="mt-4 text-sm text-white/70">Loading table…</div>
        ) : (
          <table className="mt-4 w-full text-sm">
            <thead className="text-white/60">
              <tr>
                <th className="py-2 text-left font-medium">Event</th>
                <th className="py-2 text-left font-medium">When</th>
                <th className="py-2 text-left font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t border-white/10">
                  <td className="py-2">{r.event}</td>
                  <td className="py-2 text-white/70">{r.ts}</td>
                  <td className="py-2">
                    <span
                      className={
                        r.status === 'ok'
                          ? 'rounded-full bg-emerald-500/15 px-2 py-1 text-xs text-emerald-200'
                          : 'rounded-full bg-amber-500/15 px-2 py-1 text-xs text-amber-200'
                      }
                    >
                      {r.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

