import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  eslint: {
    // Disable ESLint during builds
    ignoreDuringBuilds: true,
  },
  typescript: {
    // Disable TypeScript type checking during builds
    ignoreBuildErrors: true,
  },
  output: 'export',  // This replaces the next export command
  images: {
    unoptimized: true, // Required for static export
  },
};

export default nextConfig;
