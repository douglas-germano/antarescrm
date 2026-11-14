import { createFileRoute } from '@tanstack/react-router';
import { useState, type FormEvent } from 'react';
import { useSession } from '@/components/providers';
import useSWR from 'swr';
import { api } from '@/lib/api';
import type { Workspace } from '@/lib/types';

type Billing = {
  enabled: boolean;
  managed_by_agency: boolean;
  status: string | null;
  trial_ends_at: string | null;
  next_due_date: string | null;
  invoice_url: string | null;
  price: string | null;
  can_subscribe: boolean;
};

const statuses: Record<string, string> = {
  trialing: 'Em período de teste',
  active: 'Ativa',
  past_due: 'Em atraso',
  canceled: 'Cancelada',
};

export const Route = createFileRoute('/_app/assinatura')({
  component: SubscriptionPage,
});

function SubscriptionPage() {
  const { user, workspace, error } = useSession();
  if (error) return <p role="alert">Não foi possível carregar sua conta.</p>;
  if (!workspace || !user) return <p role="status">Carregando sua conta…</p>;
  return <WorkspaceSubscription key={workspace.id} workspace={workspace} canManage={user.role === 'owner' || user.role === 'admin'} />;
}

function WorkspaceSubscription({ workspace, canManage }: { workspace: Workspace; canManage: boolean }) {
  const { data, error, mutate } = useSWR(
    ['/billing', workspace.id],
    ([path, id]) => api<Billing>(path, { headers: { 'X-Workspace-ID': id } }),
    { shouldRetryOnError: false },
  );
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  async function subscribe(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const document = String(new FormData(event.currentTarget).get('cpf_cnpj') || '');
    setMessage('');
    setBusy(true);
    try {
      const subscription = await api<Billing>('/billing/subscribe', {
        method: 'POST',
        headers: { 'X-Workspace-ID': workspace.id },
        body: JSON.stringify({ cpf_cnpj: document }),
      });
      await mutate(subscription, { revalidate: false });
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Não foi possível iniciar a assinatura.');
    } finally {
      setBusy(false);
    }
  }

  const price = data?.price ? Number(data.price) : null;
  const invoiceUrl = data?.status !== 'canceled' && data?.invoice_url;
  return (
    <section aria-labelledby="subscription-title" className="card" style={{ maxWidth: 640, padding: '1.5rem' }}>
      <h1 id="subscription-title">Assinatura do Antares CRM</h1>
      {error && <p role="alert">Não foi possível carregar a assinatura. Atualize a página para tentar novamente.</p>}
      {!data && !error && <p role="status">Carregando assinatura…</p>}
      {data && (!data.enabled ? <p>A cobrança ainda não está disponível.</p> : data.managed_by_agency ? (
        <p>A assinatura desta conta é gerenciada pela sua agência.</p>
      ) : (
        <>
          <p>{workspace.name} · {data.status ? statuses[data.status] : 'Sem assinatura'}</p>
          {price !== null && Number.isFinite(price) && <p>{price.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })} por mês</p>}
          {data.next_due_date && <p>Vencimento da fatura: <time dateTime={data.next_due_date}>{data.next_due_date.split('-').reverse().join('/')}</time></p>}
          {!canManage ? <p>Peça a um administrador da conta para gerenciar o pagamento.</p> : (
            <>
              {invoiceUrl && <a className="btn btn-primary" href={invoiceUrl} target="_blank" rel="noopener noreferrer">Abrir fatura no Asaas</a>}
              {!invoiceUrl && !data.can_subscribe && data.next_due_date && (
                <button type="button" className="btn btn-secondary" onClick={() => void mutate()}>Atualizar fatura</button>
              )}
              {data.can_subscribe && (
                <form onSubmit={subscribe} className="auth-form">
                  <div className="field">
                    <label htmlFor="billing-document">CPF ou CNPJ do titular da cobrança</label>
                    <input id="billing-document" name="cpf_cnpj" inputMode="numeric" required minLength={11} maxLength={18} disabled={busy} />
                  </div>
                  {message && <p role="alert">{message}</p>}
                  <button className="btn btn-primary" disabled={busy}>{busy ? 'Criando assinatura…' : 'Gerar fatura no Asaas'}</button>
                </form>
              )}
            </>
          )}
        </>
      ))}
    </section>
  );
}
