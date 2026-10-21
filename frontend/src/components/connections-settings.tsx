'use client';
import { useState } from 'react';
import { CheckCheck, Loader2, Mail, MessageCircle, Power, QrCode, Smartphone } from 'lucide-react';
import { api, post } from '@/lib/api';
import { useNotify } from './providers';
import { Badge, Button, ConfirmDialog, DataState } from './ui';
import { Card, CardHeader, CardBody } from './blocks';
import { useConnection } from './whatsapp/hooks';
import { InstagramSettings } from './instagram-settings';

const DEFAULT_VARIABLES = ['EVOLUTION_API_URL', 'EVOLUTION_API_KEY', 'WHATSAPP_WEBHOOK_BASE_URL'];

function WhatsAppConnection() {
  const { notify } = useNotify();
  const connection = useConnection(true, true);
  const current = connection.current;
  const [qr, setQr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [disconnecting, setDisconnecting] = useState(false);

  async function generate(createInstance: boolean) {
    setLoading(true);
    setError('');
    try {
      const result = createInstance ? await post('/whatsapp/connection/connect', {}) : await api('/whatsapp/connection/qr');
      setQr(result.qrcode || null);
      if (createInstance) await connection.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const badge = current?.connected
    ? <Badge value="completed" label="Conectado" />
    : current?.configured
      ? <Badge value="doing" label="Desconectado" />
      : <Badge value="cancelled" label="Aguardando configuração" />;

  return (
    <Card as="section">
      <CardHeader
        title={<span className="connection-title"><MessageCircle size={18} /> WhatsApp</span>}
        description="Conexão com a Evolution API para enviar e receber mensagens."
        actions={badge}
      />
      <DataState loading={connection.loading} error={connection.error}>
        <CardBody>
          {!current?.configured ? (
            <div className="wa-settings">
              <p>Preencha estas variáveis no arquivo <code>backend/.env</code> e reinicie o backend:</p>
              <div className="wa-variables">
                {(current?.missing_variables || DEFAULT_VARIABLES).map((key: string) => <code key={key}>{key}=</code>)}
              </div>
              <p className="wa-note">
                A URL do webhook precisa ser alcançável pelo servidor Evolution. Uma Evolution remota não consegue entregar mensagens
                para o localhost do seu computador. A chave fica somente no servidor.
              </p>
            </div>
          ) : current.connected ? (
            <div className="connection-status">
              <CheckCheck size={32} color="#2e7d52" />
              <div>
                <strong>WhatsApp conectado</strong>
                {current.phone_number && <p className="muted">Número: +{current.phone_number}</p>}
              </div>
              <Button variant="danger" onClick={() => setDisconnecting(true)}><Power size={15} /> Desconectar aparelho</Button>
            </div>
          ) : (
            <div className="connection-qr">
              <div className="connection-qr-code">
                {qr ? <img src={qr} alt="QR Code para vincular o WhatsApp" /> : <QrCode size={64} strokeWidth={1} />}
              </div>
              <div className="connection-qr-text">
                <strong>Vincule um aparelho</strong>
                <p>
                  No WhatsApp do celular, abra <strong>Aparelhos conectados → Conectar um aparelho</strong> e leia o QR Code.
                  O código expira; gere um novo se necessário.
                </p>
                {error && <div className="wa-banner wa-banner-error">{error}</div>}
                <div>
                  <Button disabled={loading} onClick={() => generate(!qr)}>
                    {loading ? <Loader2 className="spin" size={16} /> : <QrCode size={16} />}
                    {qr ? 'Gerar novo QR Code' : 'Criar instância e gerar QR Code'}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </CardBody>
      </DataState>
      <ConfirmDialog
        open={disconnecting}
        onClose={() => setDisconnecting(false)}
        title="Desconectar o WhatsApp?"
        description="O aparelho será desvinculado. O histórico de conversas será preservado."
        onConfirm={async () => {
          await post('/whatsapp/connection/disconnect', {});
          setQr(null);
          await connection.refresh();
          notify('WhatsApp desconectado.');
        }}
      />
    </Card>
  );
}

const SERVER_CHANNELS: Record<string, { label: string; icon: React.ReactNode }> = {
  email: { label: 'E-mail', icon: <Mail size={18} /> },
  sms: { label: 'SMS', icon: <Smartphone size={18} /> },
};

/** Every channel and integration the platform sends through, with its state and the actions available here. */
export function ConnectionsSettings() {
  return (
    <div className="stack" aria-label="Conexões">
      <WhatsAppConnection />
      <InstagramSettings />
      <Card as="section">
        <CardHeader title="E-mail e SMS" description="Novos canais de envio e recebimento para a Caixa de entrada." />
        <CardBody>
          <ul className="connection-list">
            {Object.entries(SERVER_CHANNELS).map(([key, meta]) => (
              <li key={key}>
                <span className="connection-icon">{meta.icon}</span>
                <span className="connection-info">
                  <strong>{meta.label}</strong>
                  <small>Em breve</small>
                </span>
                <span className="deal-chip">Em breve</span>
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>
    </div>
  );
}
