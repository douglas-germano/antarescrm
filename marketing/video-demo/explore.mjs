// Passeio pelas telas do Antares local (porta 3003) em viewport de celular; salva capturas para planejar o vídeo.
// Uso: node marketing/video-demo/explore.mjs  (a partir da raiz do repositório)
import { createRequire } from 'node:module';
import { readFileSync, mkdirSync } from 'node:fs';
const require = createRequire(new URL('../../frontend/package.json', import.meta.url));
const { chromium } = require('playwright');

const BASE = 'http://127.0.0.1:3003';
const OUT = new URL('./shots/explore/', import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });
const password = readFileSync(new URL('../../.local-services/dev/demo-video-password', import.meta.url), 'utf8').trim();

const browser = await chromium.launch({ channel: 'chrome' });
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: 'pt-BR', timezoneId: 'America/Sao_Paulo' });
const page = await ctx.newPage();
await page.goto(BASE + '/login');
await page.fill('#slug', 'demo');
await page.fill('#email', 'admin@antarescrm.local');
await page.fill('#password', password);
await page.click('button[type=submit]');
await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 20000 });
for (const path of ['/', '/mensagens', '/crm', '/contatos', '/tarefas', '/agenda', '/formularios', '/funis', '/relatorios', '/automacoes']) {
  await page.goto(BASE + path);
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(800);
  await page.screenshot({ path: OUT + (path === '/' ? 'home' : path.slice(1)) + '.png', fullPage: false });
  console.log('ok', path);
}
await browser.close();
