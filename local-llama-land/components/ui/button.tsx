import React from 'react';

type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost';
};

export function Button({ variant = 'primary', className = '', ...props }: Props) {
  const base =
    'inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition disabled:opacity-50 disabled:cursor-not-allowed';
  const styles =
    variant === 'primary'
      ? 'bg-white text-black hover:bg-white/90'
      : variant === 'secondary'
        ? 'bg-white/10 text-white hover:bg-white/15 border border-white/10'
        : 'bg-transparent text-white hover:bg-white/10';

  return <button className={`${base} ${styles} ${className}`} {...props} />;
}

