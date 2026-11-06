import { useState } from 'react';
import { Plug } from 'lucide-react';
import { Card, CardBody, CardHeader } from '@/components/blocks';
import { Badge, Button, DataState } from '@/components/ui';
import { useSearchParams } from '@/lib/navigation';
import { api, post, useData } from '@/lib/api';

type Connection = { available: boolean; connected: boolean; state: 'idle' | 'authorizing' | 'failed' };
const endpoint = '/atlas/connection';

export function AtlasConnectionSettings() {
  const { data, error, isLoading } = useData<Connection>(endpoint);
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState('');
  const search = useSearchParams();

  async function connect() {
    setSubmitting(true);
    setFailure('');
    try {
      const result = await post<{ authorization_url: string }>(endpoint, {});
      const url = new URL(result.authorization_url);
      if (url.origin !== 'https://auth.openai.com') throw new Error('Endereço de autorização inválido.');
      window.location.assign(url.href);
    } catch (err) {
      setFailure((err as Error).message);
      setSubmitting(false);
    }
  }

  return <Card as="section">
    <CardHeader title={<span className="connection-title"><Plug size={18} /> ChatGPT</span>}
      description="Autorize o Atlas a usar seu plano do ChatGPT neste workspace."
      actions={data && <Badge value={data.connected ? 'completed' : 'cancelled'}
        label={data.connected ? 'Conectado' : 'Desconectado'} />} />
    <DataState loading={isLoading} error={error}>
      <CardBody>
        <div className="wa-settings">
          <p>Para autorizar, abra o Antares no computador onde o servidor está rodando.</p>
          {data && !data.available && <p role="status">A conexão com o ChatGPT ainda precisa ser configurada.</p>}
          {(data?.state === 'failed' || search.get('chatgpt') === 'failed') &&
            <p role="alert">A autorização não foi concluída. Tente novamente.</p>}
          {failure && <p role="alert">{failure}</p>}
          <div><Button disabled={!data?.available || submitting} onClick={() => void connect()}>
            {data?.connected ? 'Reconectar ChatGPT' : 'Conectar ChatGPT'}
          </Button></div>
        </div>
      </CardBody>
    </DataState>
  </Card>;
}

const playbookFields = [
  { key: 'offer', label: 'O que a empresa oferece', limit: 3000, placeholder: 'Serviços, público e informações comerciais confirmadas.' },
  { key: 'questions', label: 'Perguntas de qualificação', limit: 2000, placeholder: 'O que o Atlas deve perguntar antes de propor um próximo passo.' },
  { key: 'rules', label: 'Regras de atendimento', limit: 2000, placeholder: 'O que o Atlas pode confirmar, oferecer ou combinar.' },
  { key: 'handoff', label: 'Quando chamar uma pessoa', limit: 2000, placeholder: 'Ex.: pedidos de orçamento, reclamações ou dúvidas fora do roteiro.' },
] as const;
type Playbook = Partial<Record<typeof playbookFields[number]['key'], string>>;

export function AtlasSettings() {
  const path = '/atlas/playbook';
  const { data, error, isLoading, mutate } = useData<Playbook>(path);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    setSaving(true);
    setNotice('');
    try {
      const result = await api<Playbook>(path, { method: 'PATCH', body: JSON.stringify(values) });
      await mutate(result, { revalidate: false });
      setNotice('Roteiro salvo.');
    } catch (err) {
      setNotice((err as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return <Card as="section">
    <CardHeader title="Roteiro de atendimento" description="Estas orientações valem para as conversas atribuídas ao Atlas neste workspace." />
    <DataState loading={isLoading} error={error}>
      <CardBody>
        {data && <form className="wa-settings" onSubmit={save}>
          {playbookFields.map(field => <div className="field" key={field.key}>
            <label htmlFor={`atlas-${field.key}`}>{field.label}</label>
            <textarea id={`atlas-${field.key}`} name={field.key} maxLength={field.limit} rows={3}
              defaultValue={data[field.key] ?? ''} placeholder={field.placeholder} />
          </div>)}
          <div><Button type="submit" disabled={saving}>{saving ? 'Salvando…' : 'Salvar roteiro'}</Button></div>
          {notice && <p role="status">{notice}</p>}
        </form>}
      </CardBody>
    </DataState>
  </Card>;
}
