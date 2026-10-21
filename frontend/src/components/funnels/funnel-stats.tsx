'use client';
import { Eye, Percent, Target, Users } from 'lucide-react';
import { DataState, StatCard } from '@/components/ui';
import { Card, CardHeader } from '@/components/blocks';
import { useData } from '@/lib/api';
import { KIND_LABELS, type FunnelStats } from './types';

const pct = (value: number) => (value * 100).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + '%';

export function FunnelStatsTab({ funnelId }: { funnelId: string }) {
  const stats = useData<FunnelStats>(`/funnels/${funnelId}/stats`);
  const s = stats.data;
  return <DataState loading={stats.isLoading} error={stats.error}>
    {s && <div className="stack" style={{ marginTop: 'var(--space-4)' }}>
      <div className="stat-grid">
        <StatCard label="Visitantes" value={s.visitors.toLocaleString('pt-BR')} detail="Na primeira página" icon={<Users size={16} />} />
        <StatCard label="Conversões" value={s.conversions.toLocaleString('pt-BR')} detail="Formulários enviados" icon={<Target size={16} />} />
        <StatCard label="Taxa de conversão" value={pct(s.conversion_rate)} detail="Conversões ÷ visitantes" icon={<Percent size={16} />} />
        <StatCard label="Visualizações" value={s.steps.reduce((sum, row) => sum + row.views, 0).toLocaleString('pt-BR')} detail="Todas as páginas" icon={<Eye size={16} />} />
      </div>
      <Card as="section"><CardHeader title="Desempenho por página" />
        <div className="table-wrap"><table className="data-table">
          <thead><tr><th>Página</th><th>Tipo</th><th>Visitantes</th><th>Visualizações</th><th>Conversões</th><th>Conversão</th><th>Abandono</th></tr></thead>
          <tbody>{s.steps.map((row, i) => <tr key={row.step_id}>
            <td><strong>{i + 1}. {row.name}</strong></td><td>{KIND_LABELS[row.kind]}</td><td>{row.visitors}</td><td>{row.views}</td><td>{row.conversions}</td>
            <td>{row.visitors ? pct(row.conversion_rate) : '—'}</td><td>{i > 0 && row.visitors ? pct(row.drop_off) : '—'}</td>
          </tr>)}</tbody>
        </table></div>
      </Card>
      <p className="muted">Visitantes são contados uma vez por página e por pessoa. O abandono compara com a página anterior. Os números começam após a publicação.</p>
    </div>}
  </DataState>;
}
