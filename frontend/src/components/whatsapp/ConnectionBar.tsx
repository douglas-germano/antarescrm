import { Link } from '@tanstack/react-router';
import { Instagram, MessageCircle } from 'lucide-react';
import type { Row } from '@/lib/types';

function describe(connection?: Row) {
  if (connection?.connected) return 'WhatsApp conectado' + (connection.phone_number ? ' · +' + connection.phone_number : '');
  if (connection?.configured) return 'WhatsApp desconectado · reconecte em Configurações › Conexões';
  return 'WhatsApp aguardando configuração no servidor';
}

/** One icon per channel with a green or grey dot; the name and state show on hover. Admins jump to Conexões. */
export function ConnectionBar({ connection, instagram, canManage }: { connection?: Row; instagram?: { configured: boolean; connected: boolean } | null; canManage: boolean }) {
  const channels = [
    { key: 'whatsapp', icon: <MessageCircle size={16} />, online: Boolean(connection?.connected), label: describe(connection) },
    ...(instagram?.configured || instagram?.connected ? [{
      key: 'instagram', icon: <Instagram size={16} />, online: Boolean(instagram?.connected),
      label: instagram?.connected ? 'Instagram conectado' : 'Instagram desconectado · reconecte em Configurações › Conexões',
    }] : []),
  ];
  return (
    <div className="wa-connection-controls">
      {channels.map((c) => {
        const content = <>{c.icon}<span className={'wa-dot' + (c.online ? ' online' : '')} aria-hidden /></>;
        return canManage
          ? <Link key={c.key} className={'connection-icon ' + c.key} to="/configuracoes" search={{"tab": "conexoes"}} aria-label={c.label} data-tip={c.label}>{content}</Link>
          : <span key={c.key} className={'connection-icon ' + c.key} role="status" aria-label={c.label} data-tip={c.label}>{content}</span>;
      })}
    </div>
  );
}
