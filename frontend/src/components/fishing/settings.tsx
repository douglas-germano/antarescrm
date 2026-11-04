import { useEffect, useState } from 'react';
import { api, useData } from '@/lib/api';
import { useNotify } from '@/components/providers';
import { Button, DataState } from '@/components/ui';
import type { FishingSettings as Settings } from './types';
import './fishing.css';

export function FishingSettings() {
  const { data, error, isLoading, mutate } = useData<Settings>('/fishing/settings');
  const [form, setForm] = useState<Settings>();
  const [busy, setBusy] = useState(false);
  const { notify } = useNotify();
  useEffect(() => { if (data) setForm(data); }, [data]);
  function change<K extends keyof Settings>(key: K, value: Settings[K]) {
    setForm(current => current ? { ...current, [key]: value } : current);
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!form) return;
    setBusy(true);
    try {
      const { provider_ready: _ready, ...values } = form;
      // Read responses include record metadata; send only the editable settings.
      const keys = ['enabled', 'brand_name', 'brand_profile', 'tone', 'examples', 'allowed_topics', 'forbidden_words', 'blocked_authors', 'own_username', 'objective', 'score_threshold', 'daily_limit', 'daily_ai_limit'];
      await api('/fishing/settings', { method: 'PATCH', body: JSON.stringify(Object.fromEntries(Object.entries(values).filter(([key]) => keys.includes(key)))) });
      await mutate(); notify('Configurações da Pesca salvas.');
    } catch (err) { notify((err as Error).message, 'error'); }
    finally { setBusy(false); }
  }
  return <DataState loading={isLoading} error={error}>
    {form && <form className="fishing-settings" onSubmit={save}>
      <p className="fishing-note">O Copiloto recebe o perfil da marca, o post que você adicionar e os últimos comentários da Pesca. Esses dados são enviados à IA pelo OpenRouter para avaliar o post e escrever sugestões.</p>
      {!form.provider_ready && <p className="fishing-note" role="status">A conexão de IA ainda precisa ser configurada no servidor pelo administrador da plataforma.</p>}
      <label className="fishing-check"><input type="checkbox" checked={form.enabled} onChange={e => change('enabled', e.target.checked)} />Habilitar a Pesca e o processamento desses dados pela IA</label>
      <div className="fishing-form-grid">
        <label>Nome da marca<input required maxLength={150} value={form.brand_name} onChange={e => change('brand_name', e.target.value)} /></label>
        <label>Perfil da própria marca (sem @)<input maxLength={30} pattern="[a-zA-Z0-9_.]*" value={form.own_username} onChange={e => change('own_username', e.target.value)} /></label>
      </div>
      <label>O que a marca faz e para quem<textarea required maxLength={3000} rows={4} value={form.brand_profile} onChange={e => change('brand_profile', e.target.value)} placeholder="Descreva o negócio, o público e o que torna uma conversa relevante." /></label>
      <label>Tom de voz<input required maxLength={300} value={form.tone} onChange={e => change('tone', e.target.value)} placeholder="Ex.: próximo, curioso e objetivo" /></label>
      <label>Exemplos de comentários da marca<textarea maxLength={2000} rows={3} value={form.examples} onChange={e => change('examples', e.target.value)} /></label>
      <label>Assuntos permitidos e assuntos a evitar<textarea maxLength={2000} rows={3} value={form.allowed_topics} onChange={e => change('allowed_topics', e.target.value)} /></label>
      <label>Palavras proibidas (uma por linha)<textarea rows={3} value={form.forbidden_words.join('\n')} onChange={e => change('forbidden_words', e.target.value.split('\n'))} onBlur={() => change('forbidden_words', form.forbidden_words.map(w => w.trim()).filter(Boolean))} /></label>
      <label>Perfis bloqueados (um por linha, sem @)<textarea rows={3} value={form.blocked_authors.join('\n')} onChange={e => change('blocked_authors', e.target.value.split('\n'))} onBlur={() => change('blocked_authors', form.blocked_authors.map(w => w.trim().replace(/^@/, '')).filter(Boolean))} /></label>
      <div className="fishing-form-grid">
        <label>Objetivo<select value={form.objective} onChange={e => change('objective', e.target.value)}><option value="visitas">Visitas ao perfil</option><option value="seguidores">Seguidores</option><option value="dms">Conversas por DM</option></select></label>
        <label>Nota mínima<input type="number" required min={1} max={100} value={form.score_threshold} onChange={e => change('score_threshold', Number(e.target.value))} /></label>
        <label>Comentários por dia<input type="number" required min={1} max={100} value={form.daily_limit} onChange={e => change('daily_limit', Number(e.target.value))} /></label>
        <label>Chamadas de IA por dia<input type="number" required min={1} max={500} value={form.daily_ai_limit} onChange={e => change('daily_ai_limit', Number(e.target.value))} /></label>
      </div>
      <p className="muted">Cada post aprovado usa duas chamadas: avaliação e rascunho. Gerar outras opções também consome chamadas. O limite diário segue o fuso da conta.</p>
      <Button type="submit" disabled={busy}>{busy ? 'Salvando…' : 'Salvar configurações'}</Button>
    </form>}
  </DataState>;
}
