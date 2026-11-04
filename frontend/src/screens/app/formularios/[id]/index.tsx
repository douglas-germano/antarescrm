import { useParams } from '@tanstack/react-router';

import { useData } from '@/lib/api';
import { DataState } from '@/components/ui';
import { FormBuilder } from '@/components/forms/form-builder';
import type { Row } from '@/lib/types';

export default function FormBuilderPage() {
  const { id } = useParams({ from: '/_app/formularios/$id' });
  const forms = useData<Row>('/forms/' + id);
  const stages = useData<{ items: Row[] }>('/pipeline/stages');
  const form = forms.data;
  return <DataState loading={forms.isLoading || stages.isLoading} error={forms.error || stages.error}>
    {form && stages.data && <FormBuilder key={form.id} form={form} stages={stages.data.items} />}
  </DataState>;
}
