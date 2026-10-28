// Captura as telas do roteiro em 390×844 @3x e grava as posições dos alvos (toques/destaques) em shots/targets.json.
// Uso: node marketing/video-demo/capture.mjs  (a partir da raiz, com o Antares local na porta 3003)
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
const require = createRequire(new URL('../../frontend/package.json', import.meta.url));
const { chromium } = require('playwright');

const BASE = 'http://127.0.0.1:3003';
const OUT = new URL('./shots/', import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });
const password = readFileSync(new URL('../../.local-services/dev/demo-video-password', import.meta.url), 'utf8').trim();
const targets = {};

const browser = await chromium.launch({ channel: 'chrome' });
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, locale: 'pt-BR', timezoneId: 'America/Sao_Paulo' });
const page = await ctx.newPage();

async function rect(name, locator) {
  const b = await locator.first().boundingBox();
  if (b) targets[name] = b;
}
async function shot(name) {
  await page.waitForTimeout(700);
  await page.screenshot({ path: OUT + name + '.png' });
  console.log('shot', name);
}

// Estado inicial do banco de teste: Maria com 2 não lidas e sem resposta enviada.
const { execFileSync } = await import('node:child_process');
const sql = (q) => execFileSync('psql', ['-q', 'antares_test_video', '-c', q]);
sql("delete from whatsapp_messages where provider_id='video-reply-maria'");
sql("update whatsapp_conversations set unread_count=2, last_message_preview='Quanto custa o pacote de 10 sessões?' where contact_name='Maria Souza'");

await page.goto(BASE + '/login');
await page.fill('#slug', 'demo');
await page.fill('#email', 'admin@antarescrm.local');
await page.fill('#password', password);
await page.click('button[type=submit]');
await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 20000 });

// 1. Caixa de entrada
await page.goto(BASE + '/mensagens');
await page.waitForLoadState('networkidle').catch(() => {});
await rect('inbox_maria', page.getByText('Maria Souza', { exact: true }));
await rect('inbox_list', page.getByText('Clínica Bem Estar', { exact: true }));
await shot('01_inbox');

// 2. Conversa da Maria + resposta digitada (não enviada)
await page.getByText('Maria Souza', { exact: true }).first().click();
await page.waitForTimeout(1200);
await shot('02_conversa');
const box = page.locator('textarea, [contenteditable=true], input[placeholder*="mensagem" i]').last();
await rect('composer', box);
await box.click().catch(() => {});
await box.fill('Oi, Maria! O pacote de 10 sessões sai por R$ 2.400, em até 3x. Quer agendar a primeira?').catch(() => {});
await shot('03_resposta');
// Resposta "enviada": gravada só no banco de teste (sem provedor de WhatsApp).
sql(`insert into whatsapp_messages (id, workspace_id, conversation_id, provider_id, direction, content, kind, status, sent_via, sent_by_id, occurred_at, created_at, updated_at)
  select gen_random_uuid()::text, c.workspace_id, c.id, 'video-reply-maria', 'out',
  'Oi, Maria! O pacote de 10 sessões sai por R$ 2.400, em até 3x. Quer agendar a primeira?', 'text', 'read', 'whatsapp',
  c.assigned_to_id, now(), now(), now() from whatsapp_conversations c where c.contact_name='Maria Souza'`);
sql("update whatsapp_conversations set unread_count=0, last_message_preview='Oi, Maria! O pacote de 10 sessões sai por R$ 2.400…' where contact_name='Maria Souza'");
await page.reload();
await page.waitForLoadState('networkidle').catch(() => {});
await page.getByText('Maria Souza', { exact: true }).first().click();
await page.waitForTimeout(1200);
await shot('03b_enviada');

// 3. Funil (quadro) — duas posições de rolagem horizontal
await page.goto(BASE + '/crm');
await page.waitForLoadState('networkidle').catch(() => {});
await page.waitForTimeout(800);
await rect('crm_card_maria', page.getByText('Pacote de 10 sessões', { exact: true }));
await shot('04_funil');
const scrolled = await page.evaluate(() => {
  const els = [...document.querySelectorAll('*')].filter((e) => e.scrollWidth > e.clientWidth + 50 && getComputedStyle(e).overflowX !== 'visible');
  const el = els.sort((a, b) => b.scrollWidth - a.scrollWidth)[0];
  if (!el) return false;
  el.scrollLeft = 310;
  return true;
});
await shot('05_funil_b');
if (scrolled) await page.evaluate(() => {
  const els = [...document.querySelectorAll('*')].filter((e) => e.scrollWidth > e.clientWidth + 50 && getComputedStyle(e).overflowX !== 'visible');
  els.sort((a, b) => b.scrollWidth - a.scrollWidth)[0].scrollLeft = 930;
});
await shot('06_funil_c');

// 4. Visão geral — "Precisa de atenção"
await page.goto(BASE + '/');
await page.waitForLoadState('networkidle').catch(() => {});
await page.getByText('Precisa de atenção').first().scrollIntoViewIfNeeded();
await page.evaluate(() => window.scrollBy(0, -60));
await page.waitForTimeout(500);
await rect('atencao', page.getByText('Precisa de atenção').first());
await rect('agendar', page.getByRole('button', { name: /Agendar/ }));
await rect('retorno_atraso', page.getByText('Retorno em atraso').first());
await shot('07_atencao');

// 5. Toque em Agendar → janela de agendamento
await page.getByRole('button', { name: /Agendar/ }).first().click();
await page.waitForTimeout(900);
await shot('08_agendar');
const save = page.getByRole('button', { name: /Salvar|Agendar|Confirmar/ }).last();
await rect('salvar', save);
// Confirma o agendamento (cria a atividade só no banco de teste) e registra o resultado real.
await save.click();
await page.waitForTimeout(1500);
await shot('09_agendado');

writeFileSync(OUT + 'targets.json', JSON.stringify(targets, null, 1));
console.log(JSON.stringify(targets));
await browser.close();
