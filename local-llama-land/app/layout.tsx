import './globals.css';
import type { Metadata } from 'next';
import { Navbar } from '../components/navbar';

export const metadata: Metadata = {
  title: 'Local Llama Land',
  description: 'A clean, deterministic fake social website for Sentience demos.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Navbar />
        <main className="mx-auto max-w-5xl px-6 py-10">{children}</main>
      </body>
    </html>
  );
}

