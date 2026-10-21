import type { NextConfig } from 'next';
import path from 'path';
const config: NextConfig = {
  poweredByHeader: false,
  distDir: process.env.NEXT_DIST_DIR || '.next',
  devIndicators: false,
  outputFileTracingRoot: path.resolve(process.cwd()),
};
export default config;
