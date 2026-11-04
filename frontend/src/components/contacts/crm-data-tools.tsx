import { useRef, useState } from 'react';
import { api, post, refreshAll } from '@/lib/api';
import { useNotify } from '@/components/providers';
import { Popover } from '@/components/ui';
import { Download, Upload } from 'lucide-react';
import { ContactImportDialog } from '@/components/contacts/contact-import';
import type { Field, Row } from '@/lib/types';

export const metadataFields: Field[] = [
  { name: 'tags_text', label: 'Tags (separadas por vírgula)', wide: true },
  { name: 'custom_text', label: 'Campos personalizados', type: 'textarea', wide: true, help: 'Um campo por linha, no formato campo: valor. Ex.: Segmento: Saúde' },
];
export function metadataInitial(record?: Record<string, any> | null) {
  return { ...record, tags_text: (record?.tags || []).join(', '), custom_text: Object.entries(record?.custom_fields || {}).map(([key, value]) => `${key}: ${value}`).join('\n') };
}
export function metadataPayload(data: Record<string, any>) {
  const { tags_text, custom_text, ...rest } = data;
  const fields: Record<string, string> = {};
  for (const line of String(custom_text || '').split('\n').filter(x => x.trim())) {
    const pos = line.indexOf(':');
    if (pos <= 0) throw new Error('Use campo: valor para cada campo personalizado.');
    fields[line.slice(0, pos).trim()] = line.slice(pos + 1).trim();
  }
  return { ...rest, tags: [...new Set(String(tags_text || '').split(',').map(x => x.trim()).filter(Boolean))], custom_fields: fields };
}
export function CrmDataTools({ kind }: { kind: 'contacts' | 'companies' }) {
  const input = useRef<HTMLInputElement>(null); const { notify } = useNotify(); const [busy, setBusy] = useState(false); const [importing, setImporting] = useState(false);
  const exportCsv = async () => {
    setBusy(true);
    try { const result = await api<{ csv: string; filename: string }>('/' + kind + '/export'); const url = URL.createObjectURL(new Blob(['\ufeff' + result.csv], { type: 'text/csv;charset=utf-8' })); const link = document.createElement('a'); link.href = url; link.download = result.filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
    catch (error) { notify((error as Error).message, 'error'); } finally { setBusy(false); }
  };
  return <><input ref={input} aria-label="Importar arquivo CSV" type="file" accept=".csv,text/csv" hidden onChange={async e => {
    const file = e.target.files?.[0]; if (!file) return;
    setBusy(true);
    try {
      if (file.size > 2 * 1024 * 1024) throw new Error('CSV deve ter até 2 MB.');
      const result = await post<{ imported: number }>('/' + kind + '/import', { csv: await file.text() }); await refreshAll(); notify(`${result.imported} registro(s) importado(s).`);
    } catch (error) { notify((error as Error).message, 'error'); }
    finally { setBusy(false); if (input.current) input.current.value = ''; }
  }} />
  <Popover label="Importar / exportar" align="end" panelClassName="menu-panel">{close => <>
    <button type="button" disabled={busy} onClick={() => { close(); if (kind === 'contacts') setImporting(true); else input.current?.click(); }}><Upload size={15} />{kind === 'contacts' ? 'Importar contatos' : 'Importar CSV'}</button>
    <button type="button" disabled={busy} onClick={() => { close(); exportCsv(); }}><Download size={15} />Exportar CSV / modelo</button>
  </>}</Popover>
  {kind === 'contacts' && <ContactImportDialog open={importing} onClose={() => setImporting(false)} />}
  </>;
}
