/** @type {import('next').NextConfig} */
const API_ORIGIN = process.env.PULSE_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  // The API is proxied rather than called cross-origin, so the session cookie
  // stays httpOnly and same-site and no token is ever handled by JavaScript.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default nextConfig;
