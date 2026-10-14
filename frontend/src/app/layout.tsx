import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MoodAudio Studio — Professional Audio Restoration & Spatial Processing",
  description: "Audio extraction, conservative acoustic restoration, binaural spatial processing, and verified mastering platform.",
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='46' fill='%236366f1'/><path d='M35 50 Q 42 30 50 50 T 65 50' stroke='white' stroke-width='6' fill='none' stroke-linecap='round'/></svg>"
  }
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-theme="dark">
      <body>{children}</body>
    </html>
  );
}
