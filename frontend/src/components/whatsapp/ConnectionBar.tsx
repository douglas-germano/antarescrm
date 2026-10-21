import Link from 'next/link';
import type { Row } from '@/lib/types';

function describe(connection?: Row) {
  if (connection?.connected) return { title: 'WhatsApp conectado', hint: '' };
  if (connection?.configured)
    return { title: 'WhatsApp desconectado', hint: 'Vincule um aparelho em Configurações → Conexões.' };
  return { title: 'Conexão aguardando configuração', hint: 'Defina as variáveis da Evolution API no servidor.' };
}

/** Read-only connection status; administrators reach the management screen through the same pill. */
export function ConnectionBar({ connection, canManage }: { connection?: Row; canManage: boolean }) {
  const { title, hint } = describe(connection);
  const label = connection?.phone_number ? '+' + connection.phone_number : hint;
  const content = (
    <>
      <span className={'wa-dot' + (connection?.connected ? ' online' : '')} aria-hidden />
      <span>{title}</span>
    </>
  );
  return (
    <div className="wa-connection-controls">
      {canManage ? (
        <Link className="wa-connection-status" href="/configuracoes?tab=conexoes" title={label || 'Gerenciar conexões'}>{content}</Link>
      ) : (
        <span className="wa-connection-status" role="status" title={label}>{content}</span>
      )}
    </div>
  );
}
