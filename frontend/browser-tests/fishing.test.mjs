import { before, after, test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const workspace = { id: 'workspace-fishing', name: 'Oficina', slug: 'oficina', timezone: 'America/Cuiaba' };
const settings = { enabled: true, provider_ready: true, brand_name: 'Oficina', brand_profile: 'Móveis sob medida para famílias.', tone: 'Próximo, curioso, objetivo', examples: '', allowed_topics: '', forbidden_words: [], blocked_authors: [], own_username: 'oficina', objective: 'visitas', score_threshold: 60, daily_limit: 40, daily_ai_limit: 100 };
const row = { id: '11111111-1111-4111-8111-111111111111', url: 'https://www.instagram.com/p/teste/', caption: 'Uma cozinha compacta com bancada de madeira, azulejos claros e espaço para preparar receitas em família.', author: 'arquitetura', status: 'na_fila', score: 87, reason: 'Projeto relevante para famílias que buscam soluções para cozinhas pequenas.', summary: 'A bancada de madeira integra a cozinha ao espaço de convivência.', has_image: false, opened_at: null, user_id: 'owner', published_text: null, created_at: new Date().toISOString(), drafts: [
  { id: '22222222-2222-4222-8222-222222222222', kind: 'acrescenta', text: 'Deixar as gavetas de preparo perto dessa bancada facilita a rotina na cozinha.' },
  { id: '33333333-3333-4333-8333-333333333333', kind: 'pergunta', text: 'Qual foi o maior desafio para encaixar essa bancada de madeira no espaço?' },
  { id: '44444444-4444-4444-8444-444444444444', kind: 'reacao', text: 'A madeira deixou o encontro com os azulejos ainda mais acolhedor.' },
] };
const mutations = [];
let upstream, server, browser, origin;
const listen = async server => { server.listen(0, '127.0.0.1'); await once(server, 'listening'); return server.address().port; };
before(async () => {
  upstream = http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://fixture');
    res.setHeader('Content-Type', 'application/json');
    const reply = data => res.end(JSON.stringify(data));
    let raw = ''; for await (const chunk of req) raw += chunk;
    const data = raw ? JSON.parse(raw) : {};
    if (req.method !== 'GET') mutations.push({ path: url.pathname, data });
    if (url.pathname.endsWith('/auth/login')) return reply({ access_token: 'fixture-access', refresh_token: 'fixture-refresh' });
    if (url.pathname.endsWith('/auth/me')) return reply({ workspace, user: { id: 'owner', workspace_id: workspace.id, name: 'Responsável', role: 'owner', email: 'fixture@example.test', active: true } });
    if (url.pathname.endsWith('/auth/workspaces')) return reply({ items: [workspace] });
    if (url.pathname.endsWith('/fishing/settings')) { if (req.method === 'PATCH') Object.assign(settings, data); return reply(settings); }
    if (url.pathname.endsWith('/fishing/metrics')) return reply({ counts: { [row.status]: 1 }, total: 1, published_today: row.status === 'publicado' ? 1 : 0, edit_rate: 0, approval_rate: 0, tokens: 320, cost_usd: '.0012', unknown_cost_calls: 0, ai_calls_today: 2 });
    if (url.pathname.endsWith('/fishing/posts')) {
      if (req.method === 'POST') { res.statusCode = 201; return reply({ ...row, ...data, status: 'novo' }); }
      const visible = ['todos', row.status].includes(url.searchParams.get('status'));
      return reply({ items: visible ? [row] : [], total: visible ? 1 : 0, pages: 1, page: 1, per_page: 12 });
    }
    if (url.pathname.endsWith('/open')) { row.opened_at = new Date().toISOString(); row.published_text = data.text; return reply({ post: row, warning: null }); }
    if (url.pathname.endsWith('/decide')) { row.status = data.action === 'desfazer' ? 'pulado' : data.action; return reply(row); }
    return reply({ items: [], total: 0, count: 0 });
  });
  const apiPort = await listen(upstream);
  const reservation = http.createServer(); const port = await listen(reservation); await new Promise(resolve => reservation.close(resolve));
  origin = `http://127.0.0.1:${port}`;
  let output = '';
  server = spawn(process.execPath, ['scripts/start.mjs', '--host', '127.0.0.1', '--port', String(port)], {
    env: { ...process.env, FLASK_API_URL: `http://127.0.0.1:${apiPort}/api/v1`, APP_URL: origin, COOKIE_SECURE: 'false' }, stdio: ['ignore', 'pipe', 'pipe'],
  });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { output += chunk; });
  for (let attempt = 0; attempt < 100; attempt++) {
    if (server.exitCode !== null) throw new Error(output);
    try { if ((await fetch(origin + '/login')).ok) break; } catch {}
    if (attempt === 99) throw new Error('Frontend timeout: ' + output);
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  browser = await chromium.launch({ headless: true });
});
after(async () => {
  await browser?.close();
  if (server && server.exitCode === null) { server.kill('SIGTERM'); await once(server, 'exit'); }
  if (upstream) await new Promise(resolve => upstream.close(resolve));
});

test('review, clipboard, publication confirmation, settings and mobile layout', async () => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, permissions: ['clipboard-read', 'clipboard-write'] });
  await context.route('https://www.instagram.com/**', route => route.fulfill({ contentType: 'text/html', body: '<h1>Instagram fixture</h1>' }));
  assert.equal((await context.request.post(origin + '/api/session/login', { headers: { origin }, data: { slug: 'oficina', email: 'fixture@example.test', password: 'fixture-only' } })).status(), 200);
  const page = await context.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto(origin + '/pesca');
  await page.getByRole('heading', { name: 'Pesca', exact: true }).waitFor();
  await page.getByText(row.summary, { exact: true }).waitFor();
  await mkdir('../output/playwright', { recursive: true });
  await page.screenshot({ path: '../output/playwright/pesca-desktop.png', fullPage: true });
  await page.getByRole('article').focus(); await page.keyboard.press('2');
  assert.equal(await page.getByRole('textbox', { name: 'Seu comentário' }).inputValue(), row.drafts[1].text);
  await page.getByRole('textbox', { name: 'Seu comentário' }).fill(row.drafts[1].text + ' Gostei da solução.');
  const popupPromise = page.waitForEvent('popup');
  await page.getByRole('button', { name: 'Copiar e abrir post' }).click();
  const popup = await popupPromise; await popup.waitForURL(row.url);
  await popup.close(); await page.bringToFront();
  await page.getByText('Publicou no Instagram?', { exact: true }).waitFor();
  assert.equal(row.status, 'na_fila');
  assert.ok((await page.evaluate(() => navigator.clipboard.readText())).includes('Gostei da solução.'));
  await page.getByRole('button', { name: 'Sim, publiquei' }).click();
  await page.getByRole('combobox', { name: 'Mostrar' }).selectOption('publicado');
  await page.getByRole('button', { name: 'Desfazer confirmação' }).waitFor();
  assert.equal(row.status, 'publicado');
  await page.getByRole('button', { name: 'Fontes', exact: true }).click();
  const imageInput = page.getByLabel('Imagem ou capa (opcional, até 4 MB)');
  const image = { name: 'capa.png', mimeType: 'image/png', buffer: Buffer.from('fixture-image') };
  await imageInput.setInputFiles(image);
  await page.getByAltText('Imagem selecionada').waitFor();
  await page.getByRole('button', { name: 'Remover imagem' }).click();
  assert.equal(await page.getByAltText('Imagem selecionada').count(), 0);
  await imageInput.setInputFiles(image);
  await page.getByAltText('Imagem selecionada').waitFor();
  await page.getByRole('button', { name: 'Remover imagem' }).click();
  await page.getByRole('textbox', { name: 'Link do post' }).fill('https://www.instagram.com/p/outro/');
  await page.getByRole('textbox', { name: 'Legenda do post' }).fill('Um armário com portas de madeira.');
  await page.getByRole('button', { name: 'Avaliar e gerar sugestões' }).click();
  await page.getByRole('combobox', { name: 'Mostrar' }).waitFor();
  assert.equal(mutations.find(item => item.path.endsWith('/fishing/posts')).data.caption, 'Um armário com portas de madeira.');
  await page.getByRole('link', { name: 'Configurar marca' }).click();
  await page.getByRole('textbox', { name: 'Nome da marca' }).fill('Oficina Planejada');
  await page.getByRole('button', { name: 'Salvar configurações' }).click();
  await page.getByText('Configurações da Pesca salvas.', { exact: true }).waitFor();
  assert.equal(settings.brand_name, 'Oficina Planejada');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(origin + '/pesca');
  await page.getByRole('button', { name: 'Fontes', exact: true }).click();
  await page.getByRole('textbox', { name: 'Legenda do post' }).waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false);
  await page.screenshot({ path: '../output/playwright/pesca-mobile.png', fullPage: true });
  assert.deepEqual(errors, []);
  await context.close();
});
