'use client';
import { useParams } from 'next/navigation';
import { useData } from '@/lib/api';
import { DataState } from '@/components/ui';
import { FunnelEditor } from '@/components/funnels/funnel-editor';
import type { Funnel } from '@/components/funnels/types';

export default function FunnelPage() {
  const { id } = useParams<{ id: string }>();
  const funnel = useData<Funnel>('/funnels/' + id);
  return <DataState loading={funnel.isLoading} error={funnel.error}>
    {funnel.data && <FunnelEditor key={funnel.data.id} funnel={funnel.data} />}
  </DataState>;
}
