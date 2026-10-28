// Same production settings as next.config.ts; no TypeScript compiler in the runtime image.
module.exports = {
  poweredByHeader: false,
  distDir: '.next',
  devIndicators: false,
  outputFileTracingRoot: process.cwd(),
};
