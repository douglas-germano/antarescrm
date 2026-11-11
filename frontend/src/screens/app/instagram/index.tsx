import { useEffect, useState } from 'react';
import { Link } from '@tanstack/react-router';
import { BarChart3, Images, Instagram } from 'lucide-react';
import { useData } from '@/lib/api';
import { useSession } from '@/components/providers';
import { DataState, EmptyState, PageHeader } from '@/components/ui';
import { Tabs } from '@/components/blocks';
import { PostsPanel } from '@/components/instagram/posts';
import { InsightsPanel } from '@/components/instagram/insights';
import type { Row } from '@/lib/types';

type Section = 'publicacoes' | 'metricas';
const SECTIONS: { value: Section; label: string; icon: React.ReactNode }[] = [
  { value: 'publicacoes', label: 'Publicações', icon: <Images size={15} /> },
  { value: 'metricas', label: 'Métricas', icon: <BarChart3 size={15} /> },
];

export default function InstagramPage() {
  const { user } = useSession();
  const accounts = useData<{ items: Row[] }>('/instagram/accounts');
  const items = accounts.data?.items || [];
  const [account, setAccount] = useState('');
  const [section, setSection] = useState<Section>('publicacoes');
  const [ready, setReady] = useState(false);

  // Account and tab live in the address, so a link opens the same client profile and view.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get('conta')) setAccount(q.get('conta')!);
    if (q.get('aba') === 'metricas') setSection('metricas');
    setReady(true);
  }, []);
  const selected = items.find(a => a.id === account) || items[0];
  useEffect(() => {
    if (!ready || !selected) return;
    window.history.replaceState(null, '', '/instagram?' + new URLSearchParams({ conta: selected.id, aba: section }));
  }, [ready, selected, section]);

  const picker = items.length > 1 && <select className="ig-account-picker" aria-label="Perfil do Instagram" value={selected?.id || ''} onChange={(e) => setAccount(e.target.value)}>
    {items.map(a => <option key={a.id} value={a.id}>@{a.username}{a.connected ? '' : ' (reconectar)'}</option>)}
  </select>;
  return <div className="page instagram-page">
    <PageHeader title="Instagram" aside={picker || (selected && <span className="deal-chip">@{selected.username}</span>)}
      description="Publique, agende e acompanhe os resultados de cada perfil conectado." />
    <DataState loading={accounts.isLoading} error={accounts.error}>
      {selected ? <div className="stack">
        <Tabs variant="line" label="Seções" items={SECTIONS} value={section} onChange={setSection} />
        {section === 'publicacoes' ? <PostsPanel key={selected.id} accounts={items} account={selected.id} /> : <InsightsPanel key={selected.id} account={selected} />}
      </div> : <EmptyState icon={<Instagram />} title="Nenhum Instagram conectado"
        description="Conecte os perfis profissionais dos seus clientes para publicar e acompanhar métricas."
        action={['owner', 'admin'].includes(user?.role || '') ? <Link className="btn btn-primary" to="/configuracoes" search={{ tab: 'conexoes' }}>Conectar Instagram</Link> : undefined} />}
    </DataState>
  </div>;
}
