/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The backend runs on 8000; the frontend on 3000. Rewrite /api/* on the
  // frontend so client fetch('/api/tools') reaches the FastAPI backend
  // without CORS surprises. (CORS is also configured server-side as a
  // belt-and-suspenders for direct calls in tests.)
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://127.0.0.1:8000/api/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
