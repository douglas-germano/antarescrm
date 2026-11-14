import { before, after, test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { chromium } from 'playwright';

const funnel = '11111111-1111-4111-8111-111111111111';
const workspace = { id: 'workspace-test', name: 'Conta de teste', slug: 'test', timezone: 'America/Cuiaba' };
const requests = [];
const deliveries = [];
let upstream, server, browser, origin;
const listen = async server => { server.listen(0, '127.0.0.1'); await once(server, 'listening'); return server.address().port; };
const fixture = (req, res) => {
  const url = new URL(req.url, 'http://fixture');
  requests.push(url.pathname + url.search);
  res.setHeader('Content-Type', 'application/json');
  if (url.pathname.endsWith('/public/domains/resolve')) {
    if (url.searchParams.get('host') === 'unknown.fixture.test') { res.statusCode = 404; return res.end('{}'); }
    return res.end(JSON.stringify({ funnel_id: funnel }));
  }
  if (url.pathname.endsWith('/auth/login')) return res.end(JSON.stringify({ access_token: 'fixture-access', refresh_token: 'fixture-refresh' }));
  if (url.pathname.endsWith('/auth/logout')) { res.statusCode = 204; return res.end(); }
  if (/\/whatsapp\/webhook$|\/brevo\/webhook\//.test(url.pathname) || url.pathname.includes('/public/forms/')) {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      deliveries.push({ path: url.pathname, method: req.method, body, headers: req.headers });
      res.end(JSON.stringify({ received: true }));
    });
    return;
  }
  if (url.pathname.includes('/public/funnels/') && req.method === 'GET') {
    const second = url.pathname.endsWith('/obrigado');
    return res.end(JSON.stringify({
      funnel: { id: funnel, name: 'Funil público', theme: { accent_color: '#25282b', background: '#fff', text_color: '#25282b', font: 'sans', radius: 8 } },
      step: { id: funnel, name: second ? 'Obrigado' : 'Página pública', settings: { title: 'Funil público' }, blocks: [
        { id: 'title', type: 'heading', props: { text: second ? 'Obrigado pela visita' : 'Conteúdo público sem login', level: 1 }, style: {} },
        ...(!second ? [{ id: 'next', type: 'button', props: { label: 'Continuar', action: 'next' }, style: {} }] : []),
      ] }, next_slug: second ? null : 'obrigado', forms: {},
    }));
  }
  if (url.pathname.endsWith('/view')) { res.statusCode = 204; return res.end(); }
  if (url.pathname.endsWith('/auth/me')) return res.end(JSON.stringify({ workspace, user: { id: 'owner', workspace_id: workspace.id, name: 'Responsável', email: 'fixture@example.test', role: 'owner', active: true } }));
  if (url.pathname.endsWith('/auth/workspaces')) return res.end(JSON.stringify({ items: [workspace] }));
  if (url.pathname.endsWith('/pipelines')) return res.end(JSON.stringify({ items: [{ id: 'default', name: 'Comercial' }] }));
  if (url.pathname.endsWith('/pipeline/stages')) return res.end(JSON.stringify({ items: [{ id: 'stage', name: 'Novo', color: '#25282b', probability: 50, position: 0 }] }));
  if (url.pathname.endsWith('/whatsapp/connection')) return res.end(JSON.stringify({ connected: false }));
  if (url.pathname.endsWith('/reports/follow-ups')) return res.end(JSON.stringify({ items: [], total: 0 }));
  if (url.pathname.endsWith('/opportunities')) {
    const page = Number(url.searchParams.get('page') || 1), size = Number(url.searchParams.get('per_page') || 25);
    const all = Array.from({ length: 55 }, (_, index) => ({ id: String(index), title: `Negócio ${String(index + 1).padStart(2, '0')}`, status: 'open', amount: '100.00', stage_id: 'stage', owner_id: 'owner', contact_id: null, company_id: null, expected_close_date: null, description: null, loss_reason: null }));
    return res.end(JSON.stringify({ items: all.slice((page - 1) * size, page * size), page, per_page: size, total: all.length, pages: Math.ceil(all.length / size), sources: [], summary: { amount: '5500.00', weighted: '2750.00', stages: { stage: { amount: '5500.00', count: 55 } } } }));
  }
  if (url.pathname.endsWith('/booking-calendars')) return res.end(JSON.stringify({ items: [
    { id: 'commercial', name: 'Agenda comercial', duration_minutes: 30, buffer_minutes: 0, lead_minutes: 120, active: true },
    { id: 'support', name: 'Atendimento técnico', duration_minutes: 60, buffer_minutes: 10, lead_minutes: 120, active: true },
  ], page: 1, pages: 1, per_page: 100, total: 2 }));
  if (url.pathname.endsWith('/tasks')) {
    const page = Number(url.searchParams.get('page') || 1), size = Number(url.searchParams.get('per_page') || 25);
    const searched = url.searchParams.get('search');
    const all = Array.from({ length: 55 }, (_, index) => ({ id: String(index), title: `Tarefa ${String(index + 1).padStart(2, '0')}`, status: 'todo', priority: 'medium', due_date: null, contact_id: null, assignee_id: 'owner', assignee_name: 'Responsável' }));
    const rows = searched ? all.filter(row => row.title.includes(searched)) : all;
    return res.end(JSON.stringify({ items: rows.slice((page - 1) * size, page * size), page, per_page: size, total: rows.length, pages: Math.ceil(rows.length / size) }));
  }
  return res.end(JSON.stringify({ items: [], page: 1, pages: 1, per_page: 100, total: 0 }));
};
before(async () => {
  upstream = http.createServer(fixture);
  const apiPort = await listen(upstream);
  const reservation = http.createServer();
  const port = await listen(reservation); await new Promise(resolve => reservation.close(resolve));
  origin = `http://127.0.0.1:${port}`;
  let output = '';
  server = spawn(process.execPath, ['scripts/start.mjs', '--host', '127.0.0.1', '--port', String(port)], {
    env: { ...process.env, FLASK_API_URL: `http://127.0.0.1:${apiPort}/api/v1`, APP_URL: origin, COOKIE_SECURE: 'false', INSTAGRAM_WEBHOOK_VERIFY_TOKEN: 'fixture-verify-token' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { output += chunk; });
  for (let attempt = 0; attempt < 100; attempt++) {
    if (server.exitCode !== null) throw new Error(`TanStack Start failed: ${output}`);
    try { if ((await fetch(origin + '/login')).ok) break; } catch {}
    if (attempt === 99) throw new Error(`TanStack Start timeout: ${output}`);
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) });
});
after(async () => {
  await browser?.close();
  if (server && server.exitCode === null) { server.kill('SIGTERM'); await once(server, 'exit'); }
  if (upstream) await new Promise(resolve => upstream.close(resolve));
});

test('anonymous funnel loads and navigates without any session request', async () => {
  const context = await browser.newContext(); const page = await context.newPage();
  const network = []; page.on('request', request => network.push(request.url()));
  await page.goto(`${origin}/p/${funnel}`);
  await page.getByRole('heading', { name: 'Conteúdo público sem login' }).waitFor();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByRole('heading', { name: 'Obrigado pela visita' }).waitFor();
  assert.ok(page.url().endsWith('/obrigado'));
  assert.equal(network.some(url => url.includes('/auth/me')), false);
  assert.equal(network.some(url => url.includes('/api/backend')), false);
  await context.close();
});
test('authenticated routes redirect anonymous visitors to login', async () => {
  const context = await browser.newContext(); const page = await context.newPage();
  await page.goto(origin + '/crm'); await page.waitForURL(origin + '/login');
  await context.close();
});

test('project list supports keyboard navigation and mobile menu restores focus', async () => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await context.request.post(origin + '/api/session/login', { headers: { origin }, data: { slug: 'test', email: 'fixture@example.test', password: 'fixture-only' } });
  await context.route('**/api/backend/projects?*', route => route.fulfill({ json: { items: [{ id: 'project-1', title: 'Projeto de teste', status: 'active', amount: 0, pending_approvals: 0 }], page: 1, pages: 1, total: 1, per_page: 100 } }));
  const page = await context.newPage();
  await page.goto(origin + '/projetos');
  const menu = page.getByRole('button', { name: 'Abrir menu' });
  await menu.click();
  await page.locator('.sidebar-scrim').click({ position: { x: 380, y: 400 } });
  assert.equal(await menu.evaluate(element => document.activeElement === element), true);
  await page.getByRole('tab', { name: 'Lista', exact: true }).click();
  const link = page.getByRole('link', { name: 'Projeto de teste' });
  await link.waitFor();
  await link.focus();
  await page.keyboard.press('Enter');
  await page.waitForURL('**/projetos/project-1');
  await context.close();
});

test('session endpoints preserve HttpOnly cookies, private API access and logout', async () => {
  const context = await browser.newContext();
  assert.equal((await context.request.get(origin + '/api/backend/auth/me')).status(), 401);
  const denied = await context.request.post(origin + '/api/session/login', {
    headers: { origin: 'https://foreign.fixture.test' }, data: { slug: 'test' },
  });
  assert.equal(denied.status(), 403);
  const login = await context.request.post(origin + '/api/session/login', {
    headers: { origin }, data: { slug: 'test', email: 'fixture@example.test', password: 'fixture-only' },
  });
  assert.equal(login.status(), 200);
  const cookies = await context.cookies();
  assert.equal(cookies.filter(cookie => ['crm_access', 'crm_refresh'].includes(cookie.name) && cookie.httpOnly).length, 2);
  const page = await context.newPage(); await page.goto(origin + '/tarefas');
  await page.getByText('Tarefa 01', { exact: true }).waitFor();
  assert.equal(await page.evaluate(() => /crm_access|crm_refresh/.test(document.cookie)), false);
  assert.equal((await context.request.get(origin + '/api/backend/auth/me')).status(), 200);
  assert.equal((await context.request.post(origin + '/api/session/logout', { headers: { origin }, data: {} })).status(), 200);
  assert.equal((await context.cookies()).some(cookie => ['crm_access', 'crm_refresh'].includes(cookie.name)), false);
  await page.goto(origin + '/tarefas'); await page.waitForURL(origin + '/login');
  await context.close();
});

test('public and webhook endpoints keep their URLs, dynamic parameters and raw payloads', async () => {
  const handshake = await fetch(origin + '/api/v1/instagram/webhook?hub.mode=subscribe&hub.verify_token=fixture-verify-token&hub.challenge=12345');
  assert.equal(handshake.status, 200); assert.equal(await handshake.text(), '12345');
  const body = '{ "event": "fixture", "value": "ação" }';
  const whatsapp = await fetch(origin + '/api/v1/whatsapp/webhook', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'x-webhook-secret': 'fixture-secret' }, body,
  });
  assert.equal(whatsapp.status, 200);
  assert.equal(deliveries.at(-1).body, body);
  assert.equal(deliveries.at(-1).headers['x-webhook-secret'], 'fixture-secret');
  assert.equal(deliveries.at(-1).headers.authorization, undefined);
  const form = await fetch(origin + '/api/public/forms/' + funnel);
  assert.equal(form.status, 200);
  assert.equal(deliveries.at(-1).path, '/api/v1/public/forms/' + funnel);
  const submission = await fetch(origin + '/api/public/forms/' + funnel + '/submit', {
    method: 'POST', headers: { 'Content-Type': 'application/json', origin }, body: '{"name":"Visitante"}',
  });
  assert.equal(submission.status, 200);
  assert.equal(deliveries.at(-1).path, '/api/v1/public/forms/' + funnel + '/submit');
  assert.equal(deliveries.at(-1).method, 'POST');
  const blocked = await fetch(origin + '/api/backend/auth/me', { headers: { 'x-forwarded-host': 'landing.fixture.test', cookie: 'crm_access=fixture-session' } });
  assert.equal(blocked.status, 404);
  assert.equal((await fetch(origin + '/', { headers: { 'x-forwarded-host': 'unknown.fixture.test' } })).status, 404);
});

test('router links preserve query strings, browser history, redirects and legal metadata', async () => {
  const context = await browser.newContext();
  await context.addCookies([{ name: 'crm_access', value: 'fixture-session', url: origin }]);
  const page = await context.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto(origin + '/campanhas');
  await page.getByRole('button', { name: 'Nova campanha', exact: true }).click();
  await page.locator('.menu-panel').getByRole('button', { name: 'E-mail', exact: true }).click();
  await page.locator('dialog[open]').getByRole('button', { name: 'Cancelar', exact: true }).click();
  await page.locator('.sidebar').getByRole('link', { name: 'Configurações', exact: true }).click();
  await page.locator('.settings-nav').getByRole('button', { name: 'Notificações', exact: true }).click();
  await page.waitForURL(origin + '/configuracoes?tab=notificacoes');
  await page.reload();
  await page.getByRole('heading', { name: 'Notificações', exact: true }).waitFor();
  await page.goto(origin + '/whatsapp?conversation=thread-fixture');
  await page.waitForURL(origin + '/mensagens?conversation=thread-fixture');
  await page.goto(origin + '/agendamentos');
  await page.waitForURL(origin + '/configuracoes?tab=agendamento');
  await page.goto(origin + '/termos');
  assert.equal(await page.title(), 'Termos de Serviço · Antares CRM');
  assert.ok(await page.locator('link[rel=canonical]').getAttribute('href'));
  await page.getByRole('link', { name: 'Política de Privacidade', exact: true }).first().click();
  await page.waitForURL(origin + '/privacidade');
  await page.goBack(); await page.waitForURL(origin + '/termos');
  assert.deepEqual(errors, []);
  await context.close();
});

test('detail routes load their own screens and parameters instead of their list screens', async () => {
  const context = await browser.newContext();
  await context.addCookies([{ name: 'crm_access', value: 'fixture-session', url: origin }]);
  const page = await context.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  for (const [screen, api] of [['formularios', 'forms'], ['funis', 'funnels'], ['projetos', 'projects']]) {
    const message = 'Detalhe fixture: ' + screen;
    await page.route(`**/api/backend/${api}/${funnel}`, route => route.fulfill({
      status: 404, contentType: 'application/json', body: JSON.stringify({ error: { message } }),
    }));
    await page.goto(`${origin}/${screen}/${funnel}`);
    await page.getByText(message, { exact: true }).waitFor();
  }
  await page.goto(`${origin}/automacoes/${funnel}`);
  await page.getByRole('heading', { name: 'Automação não encontrada', exact: true }).waitFor();
  assert.deepEqual(errors, []);
  await context.close();
});

test('internal navigation keeps the shell and current content while preparing a slow destination', async () => {
  const context = await browser.newContext();
  await context.addCookies([{ name: 'crm_access', value: 'fixture-session', url: origin }]);
  const page = await context.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto(origin + '/crm');
  await page.getByText('Negócio 01', { exact: true }).waitFor();
  await page.evaluate(() => { window.__navigationDocument = 'same-document'; });
  const sidebar = await page.locator('.sidebar').elementHandle();
  let release;
  const slow = new Promise(resolve => { release = resolve; });
  await page.route('**/api/backend/tasks?**', async route => { await slow; await route.continue(); });
  const documentRequests = [];
  page.on('request', request => { if (request.isNavigationRequest()) documentRequests.push(request.url()); });
  await page.locator('.sidebar').getByRole('link', { name: 'Tarefas', exact: true }).click();
  await page.getByRole('progressbar', { name: 'Abrindo tela' }).waitFor();
  assert.equal(await page.getByText('Negócio 01', { exact: true }).isVisible(), true);
  assert.equal(await sidebar.evaluate(node => node.isConnected), true);
  release();
  await page.waitForURL(origin + '/tarefas');
  await page.getByText('Tarefa 01', { exact: true }).waitFor();
  assert.equal(await page.evaluate(() => window.__navigationDocument), 'same-document');
  assert.equal(await sidebar.evaluate(node => node.isConnected), true);
  assert.equal(await page.getByText('Carregando…', { exact: true }).count(), 0);
  assert.deepEqual(documentRequests, []);
  assert.deepEqual(errors, []);
  await context.close();
});
test('task pagination fetches only the displayed page and resets on search', async () => {
  requests.length = 0;
  const context = await browser.newContext();
  await context.addCookies([{ name: 'crm_access', value: 'fixture-session', url: origin }]);
  const page = await context.newPage(); await page.goto(origin + '/tarefas');
  await page.getByText('Tarefa 01', { exact: true }).waitFor();
  const taskPages = requests.filter(url => url.startsWith('/api/v1/tasks?') && new URL(url, origin).searchParams.get('per_page') !== '1');
  assert.equal(taskPages.length, 1); // The separate open-task counter requests one row, not another full page.
  assert.equal(requests.some(url => url.startsWith('/api/v1/contacts')), false);
  await page.getByRole('button', { name: 'Próxima página' }).click();
  await page.getByText('Tarefa 26', { exact: true }).waitFor();
  assert.ok(requests.some(url => url.includes('/tasks?') && url.includes('page=2')));
  await page.getByPlaceholder('Buscar tarefa ou contato').fill('55');
  await page.getByText('Tarefa 55', { exact: true }).waitFor();
  const last = requests.filter(url => url.startsWith('/api/v1/tasks?')).at(-1);
  assert.ok(last.includes('page=1') && last.includes('search=55'));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(200);
  const overflow = await page.evaluate(() => [...document.querySelectorAll('body *')].filter(el => el.getBoundingClientRect().right > innerWidth + 1).slice(0, 8).map(el => ({ tag: el.tagName, className: el.className, right: el.getBoundingClientRect().right })));
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, JSON.stringify(overflow));
  await context.close();
});

test('customer domain root renders the public funnel and blocks CRM routes', async () => {
  const context = await browser.newContext({ extraHTTPHeaders: { 'x-forwarded-host': 'landing.fixture.test' } });
  const page = await context.newPage();
  const network = []; page.on('request', request => network.push(request.url()));
  await page.goto(origin + '/');
  await page.getByRole('heading', { name: 'Conteúdo público sem login' }).waitFor();
  assert.equal(network.some(url => url.includes('/api/backend')), false);
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByRole('heading', { name: 'Obrigado pela visita' }).waitFor();
  await page.goBack();
  await page.getByRole('heading', { name: 'Conteúdo público sem login' }).waitFor();
  assert.equal(network.some(url => url.includes('/api/backend')), false);
  const protectedResponse = await page.goto(origin + '/crm');
  assert.equal(protectedResponse.status(), 404);
  await context.close();
});

test('CRM uses server pages and retains totals across pages and views', async () => {
  const context = await browser.newContext();
  await context.addCookies([{ name: 'crm_access', value: 'fixture-session', url: origin }]);
  const page = await context.newPage(); await page.goto(origin + '/crm');
  await page.getByText('Negócio 01', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Próxima página' }).click();
  await page.getByText('Negócio 26', { exact: true }).waitFor();
  assert.ok(await page.getByText('55', { exact: true }).count() > 0);
  await page.getByRole('tab', { name: 'Lista' }).click();
  await page.getByRole('columnheader', { name: 'Negócio' }).waitFor();
  await page.getByText('Negócio 26', { exact: true }).waitFor();
  await context.close();
});

test('calendar controls keep their geometry when switching month and list views', async () => {
  const context = await browser.newContext();
  await context.addCookies([{ name: 'crm_access', value: 'fixture-session', url: origin }]);
  const page = await context.newPage(); await page.goto(origin + '/agenda');
  await page.evaluate(() => document.fonts.ready);
  const settle = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const measure = () => page.locator('.activities-page > .page-header, .activities-page > .page-header h1, .activities-page > .page-header .btn, .activities-toolbar, .activities-toolbar [role=tab], .activities-toolbar .search').evaluateAll(nodes => nodes.map(node => {
    const { x, y, width, height } = node.getBoundingClientRect();
    return { x, y, width, height };
  }));
  for (const width of [1440, 1180, 1024, 768, 720, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await page.getByRole('tab', { name: 'Mês', exact: true }).click();
    await page.evaluate(() => scrollTo(0, 0)); await settle();
    const baseline = await measure();
    if (process.env.CALENDAR_SCREENSHOT_DIR && [1440, 390].includes(width)) await page.screenshot({ path: `${process.env.CALENDAR_SCREENSHOT_DIR}/calendar-${width}.png`, fullPage: true });
    for (const label of ['Lista', 'Mês', 'Lista']) {
      await page.getByRole('tab', { name: label, exact: true }).click();
      await page.evaluate(() => scrollTo(0, 0)); await settle();
      const current = await measure(); assert.equal(current.length, baseline.length);
      current.forEach((rect, index) => Object.entries(rect).forEach(([key, value]) => {
        assert.ok(Math.abs(value - baseline[index][key]) < 1, `${width}px, ${label}: control ${index} moved ${key} from ${baseline[index][key]} to ${value}`);
      }));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `overflow at ${width}px`);
    }
  }
  await context.close();
});

test('campaigns offer both channels and models while inbox keeps only conversations', async () => {
  const context = await browser.newContext();
  await context.addCookies([{ name: 'crm_access', value: 'fixture-session', url: origin }]);
  const page = await context.newPage();
  page.on('pageerror', error => console.error('Campaign page error:', error.message));
  await page.goto(origin + '/campanhas');
  for (const [kind, channel, title, email] of [
    ['campaign', 'E-mail', 'Nova campanha de e-mail', true],
    ['campaign', 'WhatsApp', 'Nova campanha de WhatsApp', false],
    ['template', 'E-mail', 'Novo modelo de e-mail', true],
    ['template', 'WhatsApp', 'Novo modelo de WhatsApp', false],
  ]) {
    if (kind === 'template') await page.getByRole('tab', { name: /^Modelos/ }).click();
    await page.getByRole('button', { name: kind === 'campaign' ? 'Nova campanha' : 'Novo modelo', exact: true }).click();
    await page.locator('.menu-panel').getByRole('button', { name: channel, exact: true }).click();
    const dialog = page.locator('dialog[open]');
    await dialog.waitFor();
    assert.equal(await dialog.locator('h2').textContent(), title);
    assert.equal(await dialog.getByLabel('Assunto do e-mail', { exact: false }).count(), email ? 1 : 0);
    await dialog.getByRole('button', { name: 'Cancelar', exact: true }).click();
  }
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth, undefined, {timeout:2000});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `Campaign overflow at ${width}px`);
    if (process.env.CAMPAIGN_SCREENSHOT_DIR && width !== 320) await page.screenshot({ path: `${process.env.CAMPAIGN_SCREENSHOT_DIR}/campaigns-${width}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(origin + '/mensagens');
  await page.getByRole('heading', { name: 'Caixa de entrada', exact: true }).waitFor();
  assert.equal(await page.getByRole('tab', { name: 'Disparos', exact: true }).count(), 0);
  assert.equal(await page.getByRole('tab', { name: 'Modelos', exact: true }).count(), 0);
  await page.getByRole('button', { name: 'Nova conversa', exact: true }).first().waitFor();
  await context.close();
});

test('shared tooltips stay visible above table headers and work with keyboard focus', async () => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  try {
    await context.addCookies([{ name: 'crm_access', value: 'fixture-session', url: origin }]);
    await context.route('**/api/backend/campaigns?*', route => route.fulfill({ json: {
      items: [{ id: 'campaign', name: 'Campanha teste', channel: 'email', status: 'draft', archived: false, audience: {}, metrics: {}, recipient_count: 0 }],
      page: 1, per_page: 25, pages: 1, total: 1,
    } }));
    const page = await context.newPage();
    page.setDefaultTimeout(5000);
    await page.goto(origin + '/campanhas');
    const remove = page.getByRole('button', { name: 'Apagar Campanha teste' });
    const tooltip = page.getByRole('tooltip');
    for (const width of [1280, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await remove.hover();
      await tooltip.waitFor();
      assert.equal(await tooltip.textContent(), 'Apagar rascunho');
      const bounds = await tooltip.boundingBox();
      assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width);
      assert.ok(await tooltip.evaluate(element => {
        const { left, top, width, height } = element.getBoundingClientRect();
        element.style.pointerEvents = 'auto';
        const visible = document.elementFromPoint(left + width / 2, top + height / 2) === element;
        element.style.removeProperty('pointer-events');
        return visible;
      }));
      await page.keyboard.press('Escape');
      await tooltip.waitFor({ state: 'hidden' });
      await page.mouse.move(0, 0);
    }
    await page.goto(origin + '/tarefas');
    const edit = page.getByRole('button', { name: 'Editar Tarefa 01', exact: true });
    await page.keyboard.press('Tab');
    await edit.focus();
    await tooltip.waitFor();
    assert.equal(await tooltip.textContent(), 'Editar');
    await page.keyboard.press('Tab');
    await tooltip.waitFor();
    assert.equal(await tooltip.textContent(), 'Duplicar');
  } finally {
    await context.close();
  }
});

test('inbox creates deals for linked contacts, selected contacts and new contacts without leaving the chat', async () => {
  const context = await browser.newContext();
  await context.addCookies([{ name: 'crm_access', value: 'fixture-session', url: origin }]);
  const page = await context.newPage();
  const contacts = [
    { id: '11111111-1111-4111-8111-000000000001', name: 'Cliente vinculado', phone: '+5565999900001', email: 'linked@example.test', archived: false },
    { id: '11111111-1111-4111-8111-000000000002', name: 'Contato escolhido', phone: '+5565999900002', email: 'chosen@example.test', archived: false },
  ];
  const threads = [
    { id: '22222222-2222-4222-8222-000000000001', source: 'whatsapp', channel: 'whatsapp', contact_id: contacts[0].id, contact_name: contacts[0].name, phone: '5565999900001', address: '5565999900001', status: 'open' },
    { id: '22222222-2222-4222-8222-000000000002', source: 'inbox', channel: 'email', contact_id: null, address: 'sender@example.test', status: 'open' },
    { id: '22222222-2222-4222-8222-000000000003', source: 'inbox', channel: 'instagram', contact_id: null, address: 'instagram-person', display_address: '@nova.pessoa', status: 'open' },
  ];
  const sent = [];
  await page.route('**/api/backend/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname.replace('/api/backend', '');
    const fulfill = body => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/inbox') return fulfill({ items: threads });
    if (path === '/contacts') return fulfill({ items: contacts, page: 1, pages: 1, total: contacts.length, per_page: 100, tags: [], sources: [] });
    if (path.startsWith('/contacts/')) return fulfill(contacts.find(contact => contact.id === path.split('/').at(-1)));
    if (path === '/users') return fulfill({ items: [{ id: 'owner', name: 'Responsável', active: true }], page: 1, pages: 1, total: 1, per_page: 100 });
    if (path === '/pipelines') return fulfill({ items: [{ id: 'default', name: 'Principal' }, { id: 'pipeline-other', name: 'Serviços' }] });
    if (path === '/pipeline/stages') return fulfill({ items: [{ id: 'stage', name: 'Novo', pipeline_id: null }, { id: 'stage-other', name: 'Proposta', pipeline_id: 'pipeline-other' }] });
    if (path.match(/^\/inbox\/(whatsapp|inbox)\/[^/]+\/opportunities$/)) {
      const data = request.postDataJSON(); sent.push({ path, data });
      const thread = threads.find(item => item.id === path.split('/')[3]);
      if (data.contact) contacts.push({ id: '11111111-1111-4111-8111-000000000003', ...data.contact, archived: false });
      thread.contact_id = data.contact_id || contacts.at(-1).id;
      return fulfill({ opportunity: { id: data.idempotency_key, title: data.title, contact_id: thread.contact_id }, conversation: thread });
    }
    return route.continue();
  });
  await page.goto(origin + '/mensagens');
  await page.locator('.wa-item').filter({ hasText: 'Cliente vinculado' }).click();
  await page.locator('.wa-chat-head').getByRole('button', { name: 'Mais ações', exact: true }).click();
  await page.locator('.wa-chat-head').getByRole('button', { name: 'Criar negócio', exact: true }).click();
  let dialog = page.locator('dialog[open]');
  await dialog.getByLabel('Título do negócio *', { exact: true }).fill('Proposta do atendimento');
  assert.equal(await dialog.getByRole('radio').count(), 0);
  await dialog.getByLabel('Funil *', { exact: true }).selectOption('pipeline-other');
  assert.equal(await dialog.getByLabel('Etapa *', { exact: true }).inputValue(), 'stage-other');
  await dialog.getByLabel('Valor estimado (R$)', { exact: true }).fill('1250.50');
  await dialog.getByRole('button', { name: 'Criar negócio', exact: true }).click();
  await dialog.getByRole('button', { name: 'Continuar conversa', exact: true }).waitFor();
  assert.equal(sent[0].data.contact_id, contacts[0].id);
  assert.equal(sent[0].data.stage_id, 'stage-other');
  assert.equal(sent[0].data.amount, '1250.50');
  assert.equal(await dialog.getByRole('link', { name: 'Ver negócio no funil' }).getAttribute('href'), '/crm?opportunity=' + sent[0].data.idempotency_key);
  await dialog.getByRole('button', { name: 'Continuar conversa', exact: true }).click();
  assert.ok(page.url().endsWith('/mensagens'));

  await page.locator('.wa-item').filter({ hasText: 'sender@example.test' }).click();
  await page.locator('.wa-chat-head').getByRole('button', { name: 'Mais ações', exact: true }).click();
  await page.locator('.wa-chat-head').getByRole('button', { name: 'Criar negócio', exact: true }).click();
  dialog = page.locator('dialog[open]');
  await dialog.getByLabel('Usar contato cadastrado', { exact: true }).check();
  await dialog.getByRole('combobox', { name: 'Contato *', exact: true }).click();
  await dialog.getByRole('option', { name: /Contato escolhido/ }).click();
  assert.equal(await dialog.getByLabel('Título do negócio *', { exact: true }).inputValue(), 'Negócio · Contato escolhido');
  await dialog.getByRole('button', { name: 'Criar negócio', exact: true }).click();
  await dialog.getByRole('button', { name: 'Continuar conversa', exact: true }).click();
  assert.equal(sent[1].data.contact_id, contacts[1].id);

  await page.locator('.wa-item').filter({ hasText: '@nova.pessoa' }).click();
  await page.locator('.wa-chat-head').getByRole('button', { name: 'Mais ações', exact: true }).click();
  await page.locator('.wa-chat-head').getByRole('button', { name: 'Criar negócio', exact: true }).click();
  dialog = page.locator('dialog[open]');
  await dialog.getByLabel('Nome do contato *', { exact: true }).fill('Contato novo do Instagram');
  await dialog.getByLabel('E-mail do contato', { exact: true }).fill('new@example.test');
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await page.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth, undefined, { timeout: 2000 });
    assert.equal(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth + 1), true, `Dialog overflow at ${width}px`);
    if (process.env.INBOX_DEAL_SCREENSHOT_DIR && width !== 320) await page.screenshot({ path: `${process.env.INBOX_DEAL_SCREENSHOT_DIR}/inbox-deal-${width}.png`, fullPage: true });
  }
  await dialog.getByRole('button', { name: 'Criar negócio', exact: true }).click();
  await dialog.getByRole('button', { name: 'Continuar conversa', exact: true }).waitFor();
  assert.equal(sent.length, 3);
  assert.equal(sent[2].data.contact.name, 'Contato novo do Instagram');
  assert.equal(sent[2].data.contact.email, 'new@example.test');
  assert.equal(sent[2].data.contact_id, undefined);
  await context.close();
});

async function notificationFixture(context, { history = false, desktop = false, unavailable = false } = {}) {
  await context.addCookies([{ name: 'crm_access', value: 'fixture-session', url: origin }]);
  await context.addInitScript(({ desktop }) => {
    window.__nativeAlerts = []; window.__permissionRequests = 0;
    if (desktop) { try { localStorage.setItem('antares.desktop-alerts.workspace-test.owner', 'true'); localStorage.setItem('test-notification-permission', 'granted'); } catch {} }
    class FakeNotification {
      static get permission() { return localStorage.getItem('test-notification-permission') || 'default'; }
      static async requestPermission() { window.__permissionRequests++; localStorage.setItem('test-notification-permission', 'granted'); return 'granted'; }
      constructor(title, options) { window.__nativeAlerts.push({ title, options }); }
      close() { this.onclose?.(); }
    }
    Object.defineProperty(window, 'Notification', { configurable: true, value: FakeNotification });
  }, { desktop });
  const threads = [
    { id: '77777777-7777-4777-8777-000000000001', source: 'whatsapp', channel: 'whatsapp', phone: '5565999900001', address: '5565999900001', contact_name: 'Cliente WhatsApp', status: 'open' },
    { id: '77777777-7777-4777-8777-000000000002', source: 'inbox', channel: 'instagram', address: 'Cliente Instagram', contact_name: 'Cliente Instagram', status: 'open' },
  ];
  const notices = [], readIds = new Set(), reads = [];
  let serial = 0, feedRequests = 0;
  function add(index, text) {
    serial++;
    const thread = threads[index], id = `88888888-8888-4888-8888-${String(serial).padStart(12, '0')}`;
    const created_at = `2035-01-01T00:00:${String(serial).padStart(2, '0')}.000000+00:00`;
    const row = { id, source: thread.source, thread_id: thread.id, message_id: id, channel: thread.channel, sender_name: thread.contact_name, preview: text, created_at };
    notices.push(row); return row;
  }
  if (history) add(1, 'Mensagem anterior ao carregamento');
  await context.route('**/api/backend/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname.replace('/api/backend', '');
    const fulfill = body => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/inbox/notifications') {
      feedRequests++;
      if (unavailable) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ message: 'Temporariamente indisponível' }) });
      const unread = notices.filter(row => !readIds.has(row.id)), grouped = new Map();
      for (const row of unread) { const previous = grouped.get(row.thread_id); grouped.set(row.thread_id, { ...row, unread_count: (previous?.unread_count || 0) + 1 }); }
      const latest = notices.at(-1);
      return fulfill({ items: [...grouped.values()].reverse(), total_unread: unread.length, unread_threads: grouped.size, cursor: latest ? { id: latest.id, created_at: latest.created_at } : null });
    }
    if (path === '/inbox/notifications/read') {
      const data = request.postDataJSON(); reads.push(data);
      const target = notices.find(row => row.message_id === data.message_id && row.source === data.source && row.thread_id === data.thread_id);
      if (target) for (const row of notices) if (row.source === target.source && row.thread_id === target.thread_id && row.created_at <= target.created_at) readIds.add(row.id);
      return fulfill({ read: true });
    }
    if (path === '/inbox/notifications/read-all') { notices.forEach(row => readIds.add(row.id)); return fulfill({ read: true }); }
    if (path === '/inbox') return fulfill({ items: threads });
    const thread = threads.find(row => path === `/inbox/${row.source}/${row.id}`);
    if (thread) return fulfill(thread);
    const messageThread = threads.find(row => path === `/inbox/${row.source}/${row.id}/messages` || path === `/whatsapp/conversations/${row.id}/messages`);
    if (messageThread) {
      const items = notices.filter(row => row.thread_id === messageThread.id).map(row => ({ id: row.message_id, direction: 'in', content: row.preview, created_at: row.created_at, occurred_at: row.created_at, kind: 'text', status: 'received' })).reverse();
      return fulfill({ items, page: 1, pages: 1, per_page: 100, total: items.length });
    }
    return route.continue();
  });
  return { add, reads, recover: () => { unavailable = false; }, get feedRequests() { return feedRequests; } };
}

test('message alerts use settings for browser permission and preserve old unread items while opening both channels', async () => {
  const context = await browser.newContext();
  const fixture = await notificationFixture(context, { history: true });
  const page = await context.newPage(); await page.goto(origin + '/tarefas');
  await page.getByRole('link', { name: 'Caixa de entrada: 1 mensagem não lida', exact: true }).waitFor();
  assert.equal(await page.locator('.sidebar').getByRole('button', { name: /Notificações de mensagens/ }).count(), 0);
  assert.equal(await page.getByRole('button', { name: /Notificações de mensagens/ }).count(), 0);
  const inboxLink = page.locator('.sidebar').getByRole('link', { name: /^Caixa de entrada/ });
  assert.equal(await inboxLink.locator('.nav-unread-count').innerText(), '1');
  if (process.env.NOTIFICATION_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.NOTIFICATION_SCREENSHOT_DIR}/inbox-indicator-desktop.png`, fullPage: true, animations: 'disabled' });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Abrir menu', exact: true }).click();
  await inboxLink.waitFor();
  assert.equal(await inboxLink.locator('.nav-unread-count').isVisible(), true);
  if (process.env.NOTIFICATION_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.NOTIFICATION_SCREENSHOT_DIR}/inbox-indicator-mobile.png`, fullPage: true, animations: 'disabled' });
  await inboxLink.click();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole('button', { name: 'Notificações de mensagens: 1 não lidas', exact: true }).first().waitFor();
  assert.equal(await page.locator('.toast.message').count(), 0);
  assert.equal(await page.evaluate(() => window.__permissionRequests), 0);
  await page.getByRole('button', { name: 'Notificações de mensagens: 1 não lidas', exact: true }).first().click();
  let dialog = page.locator('dialog[open]');
  assert.equal(await dialog.getByRole('button', { name: /Ativar avisos|Desativar avisos/ }).count(), 0);
  await dialog.getByRole('link', { name: 'Preferências de notificações', exact: true }).click();
  await page.waitForURL(origin + '/configuracoes?tab=notificacoes');
  await page.locator('.settings-nav').getByRole('button', { name: 'Notificações', exact: true, current: 'page' }).waitFor();
  await page.getByRole('button', { name: 'Ativar avisos', exact: true }).click();
  assert.equal(await page.evaluate(() => window.__permissionRequests), 1);
  await page.getByRole('button', { name: 'Desativar avisos', exact: true }).waitFor();
  await page.reload();
  await page.getByRole('button', { name: 'Desativar avisos', exact: true }).waitFor();
  assert.equal(await page.evaluate(() => window.__permissionRequests), 0);
  fixture.add(0, 'Nova mensagem do WhatsApp');
  await page.locator('.toast.message').filter({ hasText: 'Nova mensagem do WhatsApp' }).waitFor({ timeout: 12000 });
  const popup = await page.locator('.toast-stack').boundingBox();
  assert.ok(popup.y <= 25 && popup.x + popup.width >= 1410, JSON.stringify(popup));
  if (process.env.NOTIFICATION_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.NOTIFICATION_SCREENSHOT_DIR}/message-popup-desktop.png`, fullPage: true, animations: 'disabled' });
  await page.locator('.toast.message').getByRole('link', { name: 'Abrir conversa', exact: true }).click();
  await page.waitForURL(url => url.pathname === '/mensagens' && url.searchParams.get('source') === 'whatsapp');
  await page.locator('.wa-chat-head').getByRole('heading', { name: 'Cliente WhatsApp', exact: true }).waitFor();
  await page.locator('.wa-bubble').filter({ hasText: 'Nova mensagem do WhatsApp' }).waitFor();
  await page.waitForFunction(() => document.title === '(1) Antares CRM', undefined, { timeout: 10000 });
  assert.ok(fixture.reads.some(row => row.source === 'whatsapp'));
  fixture.add(1, 'Nova mensagem do Instagram');
  await page.locator('.toast.message').filter({ hasText: 'Nova mensagem do Instagram' }).waitFor({ timeout: 12000 });
  await page.getByRole('button', { name: 'Notificações de mensagens: 2 não lidas', exact: true }).first().click();
  dialog = page.locator('dialog[open]');
  await dialog.getByRole('link').filter({ hasText: 'Cliente Instagram' }).click();
  await page.waitForURL(url => url.searchParams.get('source') === 'inbox');
  await page.locator('.wa-chat-head').getByRole('heading', { name: 'Cliente Instagram', exact: true }).waitFor();
  await page.locator('.wa-bubble').filter({ hasText: 'Nova mensagem do Instagram' }).waitFor();
  await page.waitForFunction(() => document.title === 'Antares CRM', undefined, { timeout: 10000 });
  assert.ok(fixture.reads.some(row => row.source === 'inbox'));
  // A new receive in the visible chat is read after the message loads, without creating another toast.
  await page.locator('.toast.message button[aria-label="Fechar aviso"]').evaluateAll(nodes => nodes.forEach(node => node.click()));
  fixture.add(1, 'Mensagem na conversa aberta');
  await page.locator('.wa-bubble').filter({ hasText: 'Mensagem na conversa aberta' }).waitFor({ timeout: 12000 });
  assert.equal(await page.locator('.toast.message').count(), 0);
  await page.waitForFunction(() => document.title === 'Antares CRM', undefined, { timeout: 10000 });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Voltar às conversas', exact: true }).click();
  await page.getByRole('button', { name: 'Notificações de mensagens', exact: true }).last().click();
  await page.locator('dialog[open]').getByRole('heading', { name: 'Tudo em dia' }).waitFor();
  assert.equal(await page.locator('dialog[open]').getByRole('button', { name: /Ativar avisos|Desativar avisos/ }).count(), 0);
  await page.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth && parseFloat(getComputedStyle(document.querySelector('.app-content')).marginLeft) === 0);
  if (process.env.NOTIFICATION_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.NOTIFICATION_SCREENSHOT_DIR}/notifications-mobile.png`, fullPage: true });
  await context.close();
});

test('two background tabs claim only one browser notification for the same received message', async () => {
  const context = await browser.newContext();
  const fixture = await notificationFixture(context);
  const first = await context.newPage(); await first.goto(origin + '/configuracoes?tab=notificacoes');
  await first.getByRole('button', { name: 'Ativar avisos', exact: true }).waitFor();
  const second = await context.newPage(); await second.goto(origin + '/configuracoes?tab=notificacoes');
  await second.getByRole('button', { name: 'Ativar avisos', exact: true }).waitFor();
  const ready = Date.now() + 5000;
  while (fixture.feedRequests < 2 && Date.now() < ready) await new Promise(resolve => setTimeout(resolve, 100));
  assert.ok(fixture.feedRequests >= 2);
  await first.getByRole('button', { name: 'Ativar avisos', exact: true }).click();
  await first.getByRole('button', { name: 'Desativar avisos', exact: true }).waitFor();
  await second.getByRole('button', { name: 'Desativar avisos', exact: true }).waitFor();
  await first.mouse.move(0, 0);
  if (process.env.NOTIFICATION_SCREENSHOT_DIR) await first.screenshot({ path: `${process.env.NOTIFICATION_SCREENSHOT_DIR}/notifications-settings-desktop.png`, fullPage: true, animations: 'disabled' });
  // Headless Chromium reports every tab as focused, so simulate the browser's hidden-tab signals.
  for (const page of [first, second]) await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    document.hasFocus = () => false;
    document.dispatchEvent(new Event('visibilitychange'));
  });
  const blank = await context.newPage(); await blank.goto('about:blank'); await blank.bringToFront();
  fixture.add(0, 'Uma única notificação');
  const deadline = Date.now() + 14000;
  let total = 0;
  while (Date.now() < deadline) {
    total = await first.evaluate(() => window.__nativeAlerts.length) + await second.evaluate(() => window.__nativeAlerts.length);
    if (total) break;
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  assert.equal(total, 1);
  const before = fixture.feedRequests;
  const until = Date.now() + 8000;
  while (fixture.feedRequests < before + 2 && Date.now() < until) await new Promise(resolve => setTimeout(resolve, 200));
  assert.equal(await first.evaluate(() => window.__nativeAlerts.length) + await second.evaluate(() => window.__nativeAlerts.length), 1);
  await first.bringToFront();
  await first.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' });
    document.hasFocus = () => true;
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await first.getByRole('link', { name: 'Caixa de entrada: 1 mensagem não lida', exact: true }).click();
  await first.getByRole('button', { name: 'Notificações de mensagens: 1 não lidas', exact: true }).click();
  await first.locator('dialog[open]').getByRole('button', { name: 'Marcar todas como lidas', exact: true }).click();
  await first.locator('dialog[open]').getByRole('heading', { name: 'Tudo em dia' }).waitFor();
  if (process.env.NOTIFICATION_SCREENSHOT_DIR) await first.screenshot({ path: `${process.env.NOTIFICATION_SCREENSHOT_DIR}/notifications-desktop.png`, fullPage: true });
  await first.locator('dialog[open]').getByRole('link', { name: 'Preferências de notificações', exact: true }).click();
  await first.locator('.settings-nav').getByRole('button', { name: 'Perfil', exact: true }).click();
  await first.locator('.settings-nav').getByRole('button', { name: 'Notificações', exact: true }).click();
  await first.locator('.settings-nav').getByRole('button', { name: 'Notificações', exact: true, current: 'page' }).waitFor();
  await first.getByRole('button', { name: 'Desativar avisos', exact: true }).click();
  await second.getByRole('button', { name: 'Ativar avisos', exact: true }).waitFor();
  assert.equal(await first.evaluate(() => window.__permissionRequests), 1);
  await first.setViewportSize({ width: 390, height: 844 });
  await first.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth && parseFloat(getComputedStyle(document.querySelector('.app-content')).marginLeft) === 0, undefined, { timeout: 2000 });
  if (process.env.NOTIFICATION_SCREENSHOT_DIR) await first.screenshot({ path: `${process.env.NOTIFICATION_SCREENSHOT_DIR}/notifications-settings-mobile.png`, fullPage: true });
  await context.close();
});

test('message notifications recover after a temporary API failure without presenting an empty inbox', async () => {
  const context = await browser.newContext();
  const fixture = await notificationFixture(context, { unavailable: true, history: true });
  const page = await context.newPage(); await page.goto(origin + '/mensagens');
  await page.getByRole('button', { name: 'Notificações de mensagens', exact: true }).first().click();
  const dialog = page.locator('dialog[open]');
  await dialog.getByText('Não foi possível carregar os dados', { exact: true }).waitFor();
  assert.equal(await dialog.getByRole('heading', { name: 'Tudo em dia' }).count(), 0);
  fixture.recover();
  await dialog.getByRole('link').filter({ hasText: 'Cliente Instagram' }).waitFor({ timeout: 22000 });
  assert.equal(await page.locator('.toast.message').count(), 0);
  await dialog.getByRole('button', { name: 'Fechar janela', exact: true }).click();
  fixture.add(0, 'Recebida depois da reconexão');
  await page.locator('.toast.message').filter({ hasText: 'Recebida depois da reconexão' }).waitFor({ timeout: 12000 });
  await context.close();
});

test('sales page leads account owners to their Asaas invoice', async () => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  try {
    const page = await context.newPage();
    await page.goto(origin + '/vendas');
    await page.getByRole('heading', { name: /saiba com quem falar/i }).waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);
    await page.getByRole('button', { name: 'Proposta', exact: true }).click();
    await page.getByText('Projeto de móveis sob medida').waitFor();
    await page.getByRole('button', { name: 'Retorno', exact: true }).click();
    await page.getByText('Retomar a proposta com o cliente').waitFor();
    await page.getByText('O preço é por usuário?', { exact: true }).click();
    await page.getByText('A assinatura é de R$ 197 por mês por conta (workspace).', { exact: true }).waitFor();
    await page.getByRole('link', { name: /abrir assinatura/i }).click();
    await page.waitForURL('**/login?next=assinatura');

    const billing = { enabled: true, managed_by_agency: false, status: 'trialing', price: '197.00', can_subscribe: true };
    const invoiceUrl = 'https://sandbox.asaas.com/i/test';
    await page.route('**/api/backend/billing', route => route.fulfill({ json: billing }));
    await page.route('**/api/backend/billing/subscribe', route => {
      assert.equal(route.request().headers()['x-workspace-id'], workspace.id);
      assert.deepEqual(route.request().postDataJSON(), { cpf_cnpj: '52998224725' });
      return route.fulfill({
        json: { ...billing, can_subscribe: false, invoice_url: invoiceUrl, next_due_date: '2026-11-27' },
      });
    });
    await page.getByLabel('Conta', { exact: true }).fill('test');
    await page.getByLabel('E-mail', { exact: true }).fill('fixture@example.test');
    await page.getByLabel('Senha', { exact: true }).fill('password');
    await page.getByRole('button', { name: 'Entrar', exact: true }).click();
    await page.waitForURL('**/assinatura');
    await page.getByLabel('CPF ou CNPJ').fill('52998224725');
    await page.getByRole('button', { name: 'Gerar fatura no Asaas' }).click();
    const invoice = page.getByRole('link', { name: 'Abrir fatura no Asaas' });
    await invoice.waitFor();
    assert.equal(await invoice.getAttribute('href'), invoiceUrl);
  } finally {
    await context.close();
  }
});


test('glass chrome keeps task fields solid and dialog/menu keyboard navigation usable', async () => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  try {
    await context.request.post(origin + '/api/session/login', { headers: { origin }, data: { slug: 'test', email: 'fixture@example.test', password: 'fixture-only' } });
    const page = await context.newPage();
    await page.goto(origin + '/tarefas');
    await page.getByText('Tarefa 01', { exact: true }).waitFor();
    const blur = selector => page.locator(selector).evaluate(el => getComputedStyle(el).backdropFilter);
    assert.match(await blur('.sidebar'), /blur/);
    assert.match(await blur('.page-header'), /blur/);
    assert.equal(await page.locator('.task-card').evaluate(el => getComputedStyle(el).backdropFilter), 'none');
    await page.getByRole('button', { name: 'Nova tarefa', exact: true }).click();
    const modal = page.locator('dialog[open]');
    await modal.waitFor();
    assert.match(await blur('dialog[open]'), /blur/);
    const input = modal.locator('input').first();
    assert.equal(await input.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(255, 255, 255)');
    assert.equal(await input.evaluate(el => document.activeElement === el), true);
    await input.fill('Retomar proposta');
    if (process.env.GLASS_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.GLASS_SCREENSHOT_DIR}/glass-desktop.png` });
    await page.keyboard.press('Escape');
    await modal.waitFor({ state: 'hidden' });
    await page.setViewportSize({ width: 390, height: 844 });
    const menu = page.getByRole('button', { name: 'Abrir menu', exact: true });
    await menu.click();
    await page.getByRole('button', { name: 'Fechar navegação', exact: true }).waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    if (process.env.GLASS_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.GLASS_SCREENSHOT_DIR}/glass-mobile-menu.png` });
    await page.keyboard.press('Escape');
    assert.equal(await menu.evaluate(el => document.activeElement === el), true);
    await page.getByRole('button', { name: 'Nova tarefa', exact: true }).click();
    await modal.waitFor();
    const bounds = await modal.boundingBox();
    assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= 390);
    if (process.env.GLASS_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.GLASS_SCREENSHOT_DIR}/glass-mobile-modal.png` });
    const cdp = await context.newCDPSession(page);
    await cdp.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-transparency', value: 'reduce' }] });
    assert.equal(await blur('dialog[open]'), 'none');
    assert.equal(await blur('.sidebar'), 'none');
    assert.equal(await page.locator('dialog[open]').evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(255, 250, 251)');
  } finally { await context.close(); }
});
