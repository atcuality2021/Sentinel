import type { NextConfig } from "next";

const BACKEND = process.env.SENTINEL_BACKEND_URL ?? "http://127.0.0.1:8094";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      // Auth endpoints — must go through the proxy so Set-Cookie lands on localhost:3001
      { source: "/auth/login",  destination: `${BACKEND}/login`  },
      { source: "/auth/logout", destination: `${BACKEND}/logout` },
      // Proxy JSON API and status polling to the Python backend
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
      { source: "/projects/:path*/status.json", destination: `${BACKEND}/projects/:path*/status.json` },
      // Export HTML proxies
      { source: "/projects/:path*/tasks/:taskPath*/export.html", destination: `${BACKEND}/projects/:path*/tasks/:taskPath*/export.html` },
      { source: "/projects/:path*/export.html", destination: `${BACKEND}/projects/:path*/export.html` },
    ];
  },
};

export default nextConfig;
