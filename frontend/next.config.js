/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
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
