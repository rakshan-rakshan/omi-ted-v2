/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output is for the Docker/box build. Vercel manages its own output —
  // setting standalone there breaks routing (every route 404s), so skip it on Vercel.
  output: process.env.VERCEL ? undefined : "standalone",
  /**
   * Proxy /api/* → backend.
   * Locally: http://localhost:3001
   * Railway: set BACKEND_URL env var to internal Railway backend URL
   */
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL ?? "http://localhost:3001";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
