/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output is for the Docker/box build. Vercel manages its own output —
  // setting standalone there breaks routing (every route 404s), so skip it on Vercel.
  output: process.env.VERCEL ? undefined : "standalone",
  // NOTE: /api/* is proxied by the route handler at app/api/[...path]/route.ts
  // (not a rewrite), so it can inject the BACKEND_API_KEY header server-side.
};

module.exports = nextConfig;
