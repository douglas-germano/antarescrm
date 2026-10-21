'use client';
import { useState } from 'react';
import { Building2 } from 'lucide-react';
import { useData } from '@/lib/api';
import { useSession, useNotify } from '@/components/providers';
import type { Workspace } from '@/lib/types';

export async function switchWorkspace(workspaceId: string, currentId?: string) {
  const response = await fetch('/api/session/switch', {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...(currentId ? { 'X-Workspace-ID': currentId } : {}) },
    body: JSON.stringify({ workspace_id: workspaceId }),
  });
  const body = await response.json();
  if (!response.ok) {
    if (body?.error?.code === 'account_changed') window.location.reload();
    throw new Error(body?.error?.message || 'Não foi possível entrar nesta conta.');
  }
  // A full navigation clears all account-scoped SWR data and open edit forms.
  window.location.assign('/');
}

export function WorkspaceSwitcher() {
  const { workspace, user } = useSession();
  const { data, error } = useData<{ items: Workspace[] }>(user ? '/auth/workspaces' : null);
  const { notify } = useNotify();
  const [busy, setBusy] = useState(false);
  return <div className="workspace-switcher" title={workspace?.name}>
    <Building2 size={18} aria-hidden="true" />
    <div><label htmlFor="active-workspace">Conta atual</label>
      <select id="active-workspace" aria-label="Conta atual" value={workspace?.id || ''}
        disabled={busy || !data || data.items.length < 2}
        onChange={async (event) => {
          setBusy(true);
          try { await switchWorkspace(event.target.value, workspace?.id); }
          catch (error) { notify((error as Error).message, 'error'); setBusy(false); }
        }}>
        {(data?.items || (workspace ? [workspace] : [])).map((ws) => <option key={ws.id} value={ws.id}>{ws.name}</option>)}
      </select>
      {error && <small role="alert">Falha ao listar contas.</small>}
    </div>
  </div>;
}
