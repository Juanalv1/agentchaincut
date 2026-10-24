import type { NextConfig } from "next";

// Static export: the dashboard runs from the artifact snapshot in public/demo (offline replay)
// and switches to live mode when NEXT_PUBLIC_API_URL points at `python -m api`.
const config: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default config;
