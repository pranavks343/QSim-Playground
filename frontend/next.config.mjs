import { withSentryConfig } from "@sentry/nextjs";

/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {}
};

export default withSentryConfig(nextConfig, {
  silent: true,
  webpack: {
    treeshake: {
      removeDebugLogging: true
    }
  }
});
