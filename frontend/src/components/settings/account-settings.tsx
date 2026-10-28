'use client';
import { useEffect, useState } from 'react';
import { Check, Copy, Save } from 'lucide-react';
import { patch } from '@/lib/api';
import { useSession, useNotify } from '@/components/providers';
import { Button } from '@/components/ui';
import { Card, CardHeader, CardBody } from '@/components/blocks';
import { useUnsavedGuard } from '@/components/settings/unsaved';

/** Brazilian time zones by the places people know them for. */
const ZONES: [string, string][] = [
  ['America/Sao_Paulo', 'Brasília (SP, RJ, MG, Sul, GO, DF)'],
  ['America/Bahia', 'Bahia'],
  ['America/Fortaleza', 'Fortaleza (CE, RN, PB, PI, MA)'],
  ['America/Recife', 'Recife (PE)'],
  ['America/Maceio', 'Maceió (AL, SE)'],
  ['America/Belem', 'Belém (PA leste, AP)'],
  ['America/Santarem', 'Santarém (PA oeste)'],
  ['America/Araguaina', 'Tocantins'],
  ['America/Cuiaba', 'Cuiabá (MT)'],
  ['America/Campo_Grande', 'Campo Grande (MS)'],
  ['America/Manaus', 'Manaus (AM)'],
  ['America/Porto_Velho', 'Porto Velho (RO)'],
  ['America/Boa_Vista', 'Boa Vista (RR)'],
  ['America/Rio_Branco', 'Rio Branco (AC)'],
  ['America/Noronha', 'Fernando de Noronha'],
];
const clock = (zone: string) => {
  try { return new Intl.DateTimeFormat('pt-BR', { timeZone: zone, hour: '2-digit', minute: '2-digit' }).format(new Date()); } catch { return ''; }
};

export function AccountSettings({ canManage }: { canManage: boolean }) {
  const { workspace, reload } = useSession();
  const { notify } = useNotify();
  const saved = { name: workspace?.name || '', timezone: workspace?.timezone || 'America/Sao_Paulo' };
  const [form, setForm] = useState(saved);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick((n) => n + 1), 30000); return () => clearInterval(t); }, []);
  const dirty = form.name !== saved.name || form.timezone !== saved.timezone;
  useUnsavedGuard('account', dirty);
  const zones = ZONES.some(([z]) => z === form.timezone) ? ZONES : [[form.timezone, form.timezone] as [string, string], ...ZONES];

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      await patch('/workspace', { name: form.name.trim(), timezone: form.timezone });
      await reload();
      notify('Dados da conta atualizados.');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function copySlug() {
    try {
      await navigator.clipboard.writeText(workspace?.slug || '');
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      notify('Não foi possível copiar. Selecione o texto e copie manualmente.', 'error');
    }
  }
  return (
    <div className="settings-stack">
      <Card as="section">
        <CardHeader title="Identificador da conta" description="Quem entra no Antares informa este identificador junto com o e-mail e a senha." />
        <CardBody>
          <div className="slug-box">
            <code>{workspace?.slug}</code>
            <Button variant="soft" onClick={copySlug}>{copied ? <><Check size={15} />Copiado</> : <><Copy size={15} />Copiar</>}</Button>
          </div>
        </CardBody>
      </Card>
      <Card as="section">
        <CardHeader title="Dados da conta" description="Nome da empresa e fuso usado em prazos, agenda, automações e relatórios." />
        <CardBody>
          <form className="settings-form" onSubmit={save}>
            <fieldset disabled={!canManage} className="settings-form">
              <div className="field"><label htmlFor="account-name">Nome da conta</label>
                <input id="account-name" value={form.name} required maxLength={150} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
              <div className="field"><label htmlFor="account-zone">Fuso horário</label>
                <select id="account-zone" value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })}>
                  {zones.map(([zone, label]) => <option key={zone} value={zone}>{label} · agora {clock(zone)}</option>)}
                </select></div>
            </fieldset>
            {!canManage && <p className="muted">Somente administradores podem alterar a conta.</p>}
            {error && <p className="form-error" role="alert">{error}</p>}
            {canManage && <div className="settings-actions">
              <Button type="submit" disabled={busy || !dirty || !form.name.trim()}><Save size={16} />{busy ? 'Salvando…' : 'Salvar'}</Button>
              {dirty && <Button variant="ghost" onClick={() => { setForm(saved); setError(''); }}>Descartar</Button>}
            </div>}
          </form>
        </CardBody>
      </Card>
    </div>
  );
}
