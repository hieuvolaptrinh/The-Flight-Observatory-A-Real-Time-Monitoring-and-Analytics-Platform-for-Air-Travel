import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const gateway = (process.env.API_GATEWAY_URL || "http://127.0.0.1:2002").replace(/\/$/, "");
    return [{ source: "/api/:path*", destination: gateway + "/api/:path*" }];
  },
  /* config options here */
  experimental: {
    agentFeedback: true,
    agentUpgrade: "security",
  },
  cacheComponents: true,
  partialPrefetching: true,
};

export default nextConfig;
