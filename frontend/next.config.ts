import type { NextConfig } from "next";
import { publicSettings } from "./src/lib/core/public-settings";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  skipTrailingSlashRedirect: true,

  async rewrites() {
    // FastAPI backend URL
    const apiUrl =
      publicSettings.NEXT_PUBLIC_API_URL;

    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiUrl}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
