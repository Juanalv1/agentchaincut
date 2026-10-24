import type { Metadata } from "next";
import { Space_Grotesk, Space_Mono } from "next/font/google";
import "@xyflow/react/dist/style.css";
import "./globals.css";

const display = Space_Grotesk({ subsets: ["latin"], weight: ["300", "400", "500", "600"], variable: "--font-space-grotesk" });
const mono = Space_Mono({ subsets: ["latin"], weight: ["400", "700"], variable: "--font-space-mono" });

export const metadata: Metadata = {
  title: "AgentChainCut",
  description: "Compile and prove least-privilege policies for MCP-connected AI agents.",
};

// `lang` defaults to English; the Spanish route updates it on mount (single root layout, static export).
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
