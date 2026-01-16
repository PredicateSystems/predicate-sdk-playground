import React from 'react';

type Props = React.InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
};

export function Input({ label, className = '', ...props }: Props) {
  return (
    <label className="block space-y-2">
      {label ? <div className="text-sm text-white/80">{label}</div> : null}
      <input
        className={`w-full rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/40 focus:outline-none focus:ring-2 focus:ring-white/30 ${className}`}
        {...props}
      />
    </label>
  );
}

