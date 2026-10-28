'use client';
import { BellRing } from 'lucide-react';
import { useMessageNotifications } from '@/components/inbox/message-notifications';
import { Card, CardBody, CardHeader } from '@/components/blocks';
import { Button } from '@/components/ui';

export function NotificationSettings() {
  const { browser } = useMessageNotifications();
  const enabled = browser.enabled && browser.permission === 'granted';
  return <Card as="section">
    <CardHeader title={<span className="connection-title"><BellRing size={18} /> Notificações de mensagens</span>}
      description="Preferências para seu usuário e a conta atual neste navegador." />
    <CardBody stack>
      <ul className="connection-list">
        <li>
          <span className="connection-info"><strong>Avisos do navegador</strong><small>Receba um alerta de nova mensagem enquanto o Antares estiver aberto em outra aba.</small></span>
          <span className="deal-chip">{browser.permission === 'unsupported' ? 'Indisponíveis' : browser.permission === 'denied' ? 'Bloqueados' : enabled ? 'Ativados' : 'Desativados'}</span>
        </li>
      </ul>
      {browser.permission === 'unsupported' ? <p className="muted">Os avisos do navegador estão indisponíveis neste dispositivo.</p>
        : browser.permission === 'denied' ? <p className="muted">Os avisos estão bloqueados. Para ativá-los, permita as notificações nas configurações deste site no navegador.</p>
        : <div><Button variant="secondary" disabled={browser.busy} onClick={browser.toggle}>{browser.busy ? 'Aguarde…' : enabled ? 'Desativar avisos' : 'Ativar avisos'}</Button></div>}
      <p className="muted">A Caixa de entrada continua mostrando as mensagens não lidas e os avisos internos funcionam sem permissão do navegador.</p>
      {browser.error && <p className="form-error" role="alert">{browser.error}</p>}
    </CardBody>
  </Card>;
}
