import { readFileSync, existsSync } from 'node:fs';
import { parseEnv } from 'node:util';

// Match the development env-file priority while keeping service-provided values authoritative.
const configured = {};
for (const name of ['.env', '.env.local', '.env.production', '.env.production.local']) {
  if (existsSync(name)) Object.assign(configured, parseEnv(readFileSync(name, 'utf8')));
}
for (const [key, value] of Object.entries(configured)) process.env[key] ??= value;
for (let index = 2; index < process.argv.length; index += 2) {
  const option = process.argv[index];
  const value = process.argv[index + 1];
  if (!value || !['--port', '--host', '--hostname'].includes(option)) {
    throw new Error(`Opção inválida: ${option}. Use --port ou --host.`);
  }
  process.env[option === '--port' ? 'PORT' : 'HOST'] = value;
}
process.env.NODE_ENV = 'production';
process.env.HOST ??= '127.0.0.1';
process.env.PORT ??= '3000';
await import('../.output/server/index.mjs');
