import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Scout — Visual Intelligence by CanMarket",
  description:
    "AI-powered multi-platform product analysis with visual intelligence reports",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} font-sans antialiased`}>
        <header className="bg-white border-b border-slate-200">
          <div className="max-w-[960px] mx-auto px-6 h-14 flex items-baseline gap-3">
            <span className="text-base font-semibold text-slate-900 tracking-tight">
              Scout
            </span>
            <span className="text-sm text-slate-400">by CanMarket</span>
          </div>
        </header>
        <main className="max-w-[960px] mx-auto px-6 py-10">{children}</main>
      </body>
    </html>
  );
}
