import { before, after, test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { chromium } from 'playwright';
import { auditContrast } from './contrast-audit.mjs';

// Every authenticated screen must keep text readable on the dark glass theme (WCAG AA:
// 4.5:1 for body text, 3:1 for large text). Fixtures fill lists so badges, rows and
// cards are on screen, not only empty states.
const workspace = { id: 'workspace-test', name: 'Conta de teste', slug: 'test', timezone: 'America/Cuiaba' };
const owner = { id: 'owner', workspace_id: workspace.id, name: 'Responsável', email: 'fixture@example.test', role: 'owner', active: true };
const now = new Date().toISOString();
const page = items => ({ items, page: 1, pages: 1, per_page: 100, total: items.length });
const contacts = [
  { id: 'c1', name: 'Ana Souza', email: 'ana@example.test', phone: '+5565999990000', status: 'lead', tags: ['vip'], owner_id: 'owner', created_at: now, updated_at: now },
  { id: 'c2', name: 'Bruno Lima', email: 'bruno@example.test', phone: '+5565999990001', status: 'customer', tags: [], owner_id: 'owner', created_at: now, updated_at: now },
];
const statuses = ['todo', 'in_progress', 'done', 'cancelled'];
const priorities = ['low', 'medium', 'high', 'urgent'];
const fixtures = {
  '/auth/me': { workspace, user: owner },
  '/auth/workspaces': { items: [workspace] },
  '/users': page([owner, { ...owner, id: 'member', name: 'Membro', role: 'member' }]),
  '/pipelines': { items: [{ id: 'default', name: 'Comercial' }] },
  '/pipeline/stages': { items: [{ id: 'stage', name: 'Novo', color: '#ef2f70', probability: 50, position: 0 }, { id: 'stage2', name: 'Proposta', color: '#49677d', probability: 70, position: 1 }] },
  '/whatsapp/connection': { connected: false },
  '/contacts': page(contacts),
  '/companies': page([{ id: 'co1', name: 'Empresa Alfa', domain: 'alfa.test', created_at: now, updated_at: now }]),
  '/tasks': page(statuses.map((status, index) => ({ id: 't' + index, title: 'Tarefa ' + status, status, priority: priorities[index], due_date: index === 0 ? '2020-01-01' : null, contact_id: 'c1', contact_name: 'Ana Souza', assignee_id: 'owner', assignee_name: 'Responsável' }))),
  '/opportunities': { ...page(['open', 'won', 'lost'].map((status, index) => ({ id: 'o' + index, title: 'Negócio ' + status, status, amount: '1200.00', stage_id: index ? 'stage2' : 'stage', owner_id: 'owner', contact_id: 'c1', company_id: null, expected_close_date: '2020-01-01', description: null, loss_reason: null }))), sources: [], summary: { amount: '3600.00', weighted: '2000.00', stages: { stage: { amount: '1200.00', count: 1 }, stage2: { amount: '2400.00', count: 2 } } } },
  '/projects': page([{ id: 'p1', title: 'Projeto de teste', status: 'active', amount: 1000, pending_approvals: 1, contact_name: 'Ana Souza' }, { id: 'p2', title: 'Projeto pronto', status: 'done', amount: 0, pending_approvals: 0 }]),
  '/automations': page([
    { id: 'a1', name: 'Boas-vindas', event: 'contact.created', actions: [{ kind: 'create_task', title: 'Ligar', delay_minutes: 0 }], active: true, draft: { name: 'Boas-vindas' }, stats: { runs: 3, failed: 1, last_run_at: now }, created_at: now },
    { id: 'a2', name: 'Pausada', event: 'form.submitted', actions: [{ kind: 'create_task', title: 'Responder', delay_minutes: 0 }], active: false, stats: { runs: 0, failed: 0, last_run_at: null }, created_at: now },
  ]),
  '/automations/runs': page([{ id: 'r1', rule_id: 'a1', status: 'failed', error: 'Modelo removido', created_at: now }, { id: 'r2', rule_id: 'a1', status: 'completed', created_at: now }]),
  '/campaigns': page([{ id: 'cp1', name: 'Campanha teste', channel: 'email', status: 'draft', archived: false, audience: {}, metrics: {}, recipient_count: 0 }, { id: 'cp2', name: 'Campanha enviada', channel: 'whatsapp', status: 'sent', archived: false, audience: {}, metrics: { sent: 10, delivered: 9, read: 4 }, recipient_count: 10 }]),
  '/automations/a1': {
    id: 'a1', name: 'Boas-vindas', event: 'contact.created', active: true, created_at: now, stats: { runs: 3, failed: 1, last_run_at: now },
    actions: [
      { kind: 'create_task', title: 'Ligar para o contato', delay_minutes: 60, due_days: 1 },
      { kind: 'branch', conditions: { match: 'all', items: [{ field: 'contact.tags', op: 'contains', value: 'vip' }] }, yes: [{ kind: 'add_tag', tag: 'prioridade', delay_minutes: 0 }], no: [] },
    ],
    draft: { name: 'Boas-vindas', event: 'contact.created', actions: [{ kind: 'create_task', title: 'Ligar para o contato', delay_minutes: 0 }] },
  },
  '/inbox': { items: [
    { id: 't1', source: 'inbox', channel: 'email', address: 'ana@example.test', contact_id: 'c1', contact_name: 'Ana Souza', preview: 'Pode me mandar a proposta?', unread_count: 2, status: 'open', waiting_on: 'us', waiting_since: '2020-01-01T10:00:00Z', last_message_at: now, last_inbound_at: now, has_open_deal: true, assigned_to_id: 'owner' },
    { id: 't2', source: 'inbox', channel: 'instagram', address: 'ig-1', display_address: '@bruno', preview: 'Obrigado!', unread_count: 0, status: 'open', delivery_failed: true, delivery_error: 'Janela fechada', last_message_at: now, last_inbound_at: '2020-01-01T10:00:00Z' },
  ] },
  '/inbox/summary': { first_response_median: 3600, first_response_sample: 4, period_days: 30 },
  '/inbox/inbox/t1': { id: 't1', source: 'inbox', channel: 'email', address: 'ana@example.test', contact_id: 'c1', contact_name: 'Ana Souza', status: 'open' },
  '/inbox/inbox/t1/messages': page([
    { id: 'm1', direction: 'inbound', kind: 'text', content: 'Oi, tudo bem? Pode me mandar a proposta?', created_at: '2026-11-13T10:00:00Z', occurred_at: '2026-11-13T10:00:00Z' },
    { id: 'm2', direction: 'outbound', kind: 'text', content: 'Claro, envio ainda hoje.', status: 'read', created_at: '2026-11-13T10:05:00Z', occurred_at: '2026-11-13T10:05:00Z' },
    { id: 'm3', direction: 'outbound', kind: 'text', content: 'Segue a proposta.', status: 'failed', error: 'Falha de envio', created_at: now, occurred_at: now },
  ]),
  '/forms': page([{ id: 'f1', name: 'Formulário de contato', status: 'published', submissions_count: 4, updated_at: now }]),
  '/funnels': page([{ id: 'fn1', name: 'Funil de captura', status: 'draft', steps_count: 2, updated_at: now }]),
};
let upstream, server, browser, origin;
const listen = async target => { target.listen(0, '127.0.0.1'); await once(target, 'listening'); return target.address().port; };
const respond = (req, res) => {
  const url = new URL(req.url, 'http://fixture');
  res.setHeader('Content-Type', 'application/json');
  if (url.pathname.endsWith('/auth/login')) return res.end(JSON.stringify({ access_token: 'fixture-access', refresh_token: 'fixture-refresh' }));
  const path = url.pathname.replace(/^\/api\/v1/, '');
  if (fixtures[path]) return res.end(JSON.stringify(fixtures[path]));
  if (/^\/reports\/(?!follow-ups)/.test(path)) { res.statusCode = 404; return res.end(JSON.stringify({ error: { message: 'Relatório indisponível no teste' } })); }
  return res.end(JSON.stringify(page([])));
};
before(async () => {
  upstream = http.createServer(respond);
  const apiPort = await listen(upstream);
  const reservation = http.createServer();
  const port = await listen(reservation); await new Promise(resolve => reservation.close(resolve));
  origin = `http://127.0.0.1:${port}`;
  let output = '';
  server = spawn(process.execPath, ['scripts/start.mjs', '--host', '127.0.0.1', '--port', String(port)], {
    env: { ...process.env, FLASK_API_URL: `http://127.0.0.1:${apiPort}/api/v1`, APP_URL: origin, COOKIE_SECURE: 'false' },
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

const screens = ['/', '/mensagens', '/crm', '/automacoes', '/campanhas', '/instagram', '/formularios', '/funis', '/contatos', '/empresas', '/projetos', '/tarefas', '/agenda', '/relatorios', '/configuracoes', '/assinatura'];
const settings = ['perfil', 'notificacoes', 'conta', 'equipe', 'funis', 'projetos', 'agendamento', 'atlas', 'conexoes', 'mcp', 'dominios'];
const report = failures => failures.map(item => `${item.where} "${item.text}" ${item.ratio}:1 < ${item.minimum}:1 (${item.color} on ${item.background})`).join('\n');

test('authenticated screens keep text contrast at WCAG AA on the dark theme', async () => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  await context.addCookies([{ name: 'crm_access', value: 'fixture-session', url: origin }]);
  const tab = await context.newPage();
  tab.setDefaultTimeout(5000);
  const found = [];
  const errors = []; tab.on('pageerror', error => errors.push(error.message));
  tab.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  const visit = async (label, path, prepare) => {
    await tab.goto(origin + path);
    await tab.waitForLoadState('networkidle');
    await tab.locator('#main-content :is(h1, .flow-editor)').first().waitFor().catch(async () => { throw new Error(`${label} did not render: ${errors.join('; ')} ${(await tab.locator('body').innerText().catch(() => '')).slice(0, 400)}`); });
    if (prepare) await prepare();
    await tab.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    if (process.env.CONTRAST_SCREENSHOT_DIR) await tab.screenshot({ path: `${process.env.CONTRAST_SCREENSHOT_DIR}/${label.replace(/[^a-z0-9]+/gi, '_') || 'inicio'}.png` });
    for (const item of await tab.evaluate(auditContrast)) found.push({ ...item, where: `${label}: ${item.where}` });
  };
  for (const path of screens) await visit(path, path);
  for (const name of settings) await visit('configuracoes/' + name, '/configuracoes?tab=' + name);
  await visit('crm lista', '/crm', () => tab.getByRole('tab', { name: 'Lista' }).click());
  await visit('conversa aberta', '/mensagens?conversation=t1&source=inbox', () => tab.locator('.wa-bubble').first().waitFor());
  await visit('editor de automação', '/automacoes/a1', () => tab.locator('.flow-node').first().waitFor());
  // Hover and pressed states paint their own fills; check them on the element under the pointer.
  const hovered = async (label, path, selector, prepare) => {
    await tab.goto(origin + path);
    await tab.waitForLoadState('networkidle');
    if (prepare) await prepare();
    const target = tab.locator(selector).first();
    await target.waitFor();
    await target.hover();
    await tab.waitForTimeout(250);
    const marker = `hover-${found.length}-${Math.random().toString(36).slice(2)}`;
    await target.evaluate((element, id) => element.setAttribute('data-contrast-target', id), marker);
    for (const item of await tab.evaluate(auditContrast, { root: `[data-contrast-target="${marker}"]` })) found.push({ ...item, where: `${label} (hover): ${item.where}` });
  };
  for (const [label, path, selector, prepare] of [
    ['botão', '/tarefas', '.page-header .btn'],
    ['botão secundário', '/', '.btn:not(.btn-primary)'],
    ['linha de tarefa', '/tarefas', '.task-row'],
    ['cartão do funil', '/crm', '.kanban-card', () => tab.getByRole('tab', { name: 'Quadro' }).click()],
    ['linha de automação', '/automacoes', '.flow-list-row'],
    ['aba', '/automacoes', '[role=tab]:not([aria-selected=true])'],
    ['conversa', '/mensagens', '.wa-item'],
    ['menu lateral', '/', '.sidebar nav a:not(.active)'],
  ]) await hovered(label, path, selector, prepare);
  await visit('nova campanha', '/campanhas', async () => {
    await tab.getByRole('button', { name: 'Nova campanha', exact: true }).click();
    await tab.locator('.menu-panel').getByRole('button', { name: 'E-mail', exact: true }).click();
    await tab.locator('dialog[open]').waitFor();
  });
  if (process.env.CONTRAST_REPORT) console.log(report(found));
  assert.deepEqual(found, [], `\n${report(found)}`);
  await context.close();
});

test('mobile top bar holds the menu button beside the title and stays on top while scrolling', async () => {
  const context = await browser.newContext({ viewport: { width: 390, height: 420 }, reducedMotion: 'reduce' });
  await context.addCookies([{ name: 'crm_access', value: 'fixture-session', url: origin }]);
  const tab = await context.newPage();
  for (const path of ['/tarefas', '/contatos']) {
    await tab.goto(origin + path);
    await tab.waitForLoadState('networkidle');
    const bar = tab.locator('.page-header');
    const title = bar.locator('h1');
    const menu = tab.getByRole('button', { name: 'Abrir menu' });
    await title.waitFor();
    const geometry = async () => ({ bar: await bar.boundingBox(), title: await title.boundingBox(), menu: await menu.boundingBox() });
    const check = async moment => {
      const { bar: b, title: t, menu: m } = await geometry();
      assert.ok(Math.abs(b.y) < 1, `${path} ${moment}: top bar starts at ${b.y}px`);
      assert.ok(m.y >= b.y && m.y + m.height <= b.y + b.height, `${path} ${moment}: menu button outside the top bar`);
      assert.ok(t.x >= m.x + m.width + 8, `${path} ${moment}: title overlaps the menu button`);
      assert.ok(Math.abs((t.y + t.height / 2) - (m.y + m.height / 2)) < 6, `${path} ${moment}: title and menu button are not aligned`);
    };
    await check('at the top');
    await tab.evaluate(() => scrollTo(0, document.documentElement.scrollHeight));
    await tab.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await check('after scrolling');
  }
  await context.close();
});
