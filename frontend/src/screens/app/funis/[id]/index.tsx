import { useParams } from '@tanstack/react-router';

import { useData } from '@/lib/api';
import { DataState } from '@/components/ui';
import { FunnelEditor } from '@/components/funnels/funnel-editor';
import type { Funnel } from '@/components/funnels/types';

export default function FunnelPage() {
  const { id } = useParams({ from: '/_app/funis/$id' });
  const funnel = useData<Funnel>('/funnels/' + id);
  return <DataState loading={funnel.isLoading} error={funnel.error}>
    {funnel.data && <FunnelEditor key={funnel.data.id} funnel={funnel.data} />}
  </DataState>;
}
