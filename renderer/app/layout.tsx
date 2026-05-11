import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Jarvis',
  description: 'Voice-driven desktop assistant',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
