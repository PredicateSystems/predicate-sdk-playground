export function Card({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="glass rounded-xl p-5">
      <div className="text-base font-semibold">{title}</div>
      <div className="mt-2 text-sm text-white/70">{desc}</div>
    </div>
  );
}

