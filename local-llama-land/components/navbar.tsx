import Link from 'next/link';

const NavLink = ({ href, children }: { href: string; children: React.ReactNode }) => (
  <Link href={href} className="text-sm text-white/70 hover:text-white">
    {children}
  </Link>
);

export function Navbar() {
  return (
    <header className="border-b border-white/10 bg-black/20">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
        <Link href="/" className="font-semibold tracking-tight">
          Local LLama Land
        </Link>
        <nav className="flex items-center gap-4">
          <NavLink href="/login">Login</NavLink>
          <NavLink href="/profile">Profile</NavLink>
          <NavLink href="/dashboard">Dashboard</NavLink>
          <NavLink href="/forms/onboarding">Form</NavLink>
        </nav>
      </div>
    </header>
  );
}

