import type { NextConfig } from "next";

const BACKEND = process.env.SENTINEL_BACKEND_URL ?? "http://127.0.0.1:8094";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      // Proxy JSON API and status polling to the Python backend
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
      { source: "/projects/:path*/status.json", destination: `${BACKEND}/projects/:path*/status.json` },
    ];
  },
};

export default nextConfig;
