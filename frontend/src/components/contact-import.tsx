'use client';
import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, FileUp, Loader2, SlidersHorizontal, UploadCloud } from 'lucide-react';
import { post, refreshAll } from '@/lib/api';
import { useNotify } from './providers';
import { Badge, Button, Modal } from './ui';
import type { Row } from '@/lib/types';

const MAX_BYTES = 8 * 1024 * 1024;

/** UTF-8 first; spreadsheets saved by older Excel/Outlook builds fall back to Windows-1252. */
async function readText(file: File) {
  const buffer = await file.arrayBuffer();
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(buffer);
  } catch {
    return new TextDecoder('windows-1252').decode(buffer);
  }
}

type Preview = { format: string; format_label: string; headers: string[]; mapping: Record<string, string[]>; field_labels: Record<string, string>; multi: string[];
  summary: { total: number; valid: number; invalid: number; duplicates: number; with_phone: number; with_email: number; labels: { label: string; count: number }[]; problems: { line: number; reason: string }[]; rejected_phones: Record<string, number> };
  sample: Row[] };

export function ContactImportDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { notify } = useNotify();
  const input = useRef<HTMLInputElement>(null);
  const [content, setContent] = useState('');
  const [filename, setFilename] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string[]> | null>(null);
  const [showMapping, setShowMapping] = useState(false);
  const [ignored, setIgnored] = useState<string[] | null>(null);
  const [options, setOptions] = useState({ source: 'Importação', default_ddd: '', duplicates: 'skip', create_companies: true, import_tags: true, trigger_automations: false });
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<Row | null>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    if (open) return;
    setContent(''); setFilename(''); setPreview(null); setMapping(null); setIgnored(null); setError(''); setResult(null); setShowMapping(false);
  }, [open]);

  const body = () => ({ content, filename, mapping: mapping || undefined, options: { ...options, ignored_tags: ignored || [] } });

  // Re-run the preview whenever the file, column mapping or options change.
  useEffect(() => {
    if (!content) return;
    const timer = setTimeout(async () => {
      setLoading(true); setError('');
      try {
        const data: Preview = await post('/contacts/import/preview', body());
        setPreview(data);
        if (!mapping) setMapping(data.mapping);
        if (ignored === null) setIgnored(data.summary.labels.filter((l) => l.label.startsWith('*')).map((l) => l.label));
      } catch (e) { setError((e as Error).message); setPreview(null); }
      finally { setLoading(false); }
    }, 250);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content, mapping, options.default_ddd, options.source, options.import_tags, ignored]);

  async function choose(file?: File) {
    if (!file) return;
    if (file.size > MAX_BYTES) { setError('O arquivo deve ter até 8 MB.'); return; }
    setMapping(null); setIgnored(null); setPreview(null); setResult(null); setError('');
    setFilename(file.name);
    setContent(await readText(file));
  }
  async function run() {
    setRunning(true); setError('');
    try {
      const data = await post('/contacts/import/run', body());
      setResult(data);
      await refreshAll();
      notify(`${data.imported} contato(s) importado(s).`);
    } catch (e) { setError((e as Error).message); }
    finally { setRunning(false); }
  }
  const setMap = (key: string, index: number, value: string) => setMapping((current) => {
    const list = [...((current || {})[key] || [])];
    if (value) list[index] = value; else list.splice(index, 1);
    return { ...(current || {}), [key]: list };
  });
  const summary = preview?.summary;
  const toImport = summary ? summary.valid - (options.duplicates === 'skip' ? summary.duplicates : 0) : 0;

  return (
    <Modal open={open} onClose={() => { if (!running) onClose(); }} title="Importar contatos" wide
      description="Aceita exportações do Google Contatos, Outlook, vCard (.vcf), o modelo do Antares e planilhas CSV em geral.">
      {result ? (
        <div className="import-result">
          <CheckCircle2 size={40} color="#2e7d52" />
          <h3>Importação concluída</h3>
          <dl>
            <div><dt>Novos contatos</dt><dd>{result.imported}</dd></div>
            <div><dt>Atualizados</dt><dd>{result.updated}</dd></div>
            <div><dt>Duplicados ignorados</dt><dd>{result.skipped_duplicates}</dd></div>
            <div><dt>Sem telefone ou e-mail</dt><dd>{result.skipped_invalid}</dd></div>
            <div><dt>Empresas criadas</dt><dd>{result.companies_created}</dd></div>
          </dl>
          <Button onClick={onClose}>Concluir</Button>
        </div>
      ) : (
        <div className="import-body">
          <input ref={input} type="file" hidden accept=".csv,.vcf,.txt,text/csv,text/vcard,text/plain" aria-label="Arquivo de contatos" onChange={(e) => { void choose(e.target.files?.[0]); e.target.value = ''; }} />
          <div className={'import-drop' + (dragging ? ' over' : '') + (filename ? ' filled' : '')} role="button" tabIndex={0}
            onClick={() => input.current?.click()} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') input.current?.click(); }}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); void choose(e.dataTransfer.files?.[0]); }}>
            {filename ? <FileUp size={22} /> : <UploadCloud size={26} />}
            <div>
              <strong>{filename || 'Escolha ou arraste o arquivo'}</strong>
              <small>{filename ? (preview ? `Formato detectado: ${preview.format_label}` : 'Lendo o arquivo…') : 'CSV ou vCard, até 8 MB e 10.000 contatos'}</small>
            </div>
            {loading && <Loader2 size={18} className="spin" />}
            {filename && <span className="link-btn">Trocar arquivo</span>}
          </div>

          {error && <p role="alert" className="form-error">{error}</p>}

          {preview && summary && (
            <>
              <div className="import-stats">
                <div><strong>{summary.total}</strong><span>linhas lidas</span></div>
                <div><strong>{toImport}</strong><span>serão importadas</span></div>
                <div><strong>{summary.duplicates}</strong><span>{options.duplicates === 'update' ? 'serão atualizadas' : 'duplicadas (ignoradas)'}</span></div>
                <div><strong>{summary.invalid}</strong><span>sem telefone/e-mail</span></div>
              </div>

              <div className="import-sample table-wrap">
                <table className="data-table">
                  <thead><tr><th>Nome</th><th>Telefone</th><th>E-mail</th><th>Empresa</th><th /></tr></thead>
                  <tbody>
                    {preview.sample.map((r, i) => (
                      <tr key={i}>
                        <td><strong>{r.name}</strong></td>
                        <td>{r.phones[0] || '—'}{r.phones.length > 1 && <small>+{r.phones.length - 1} número(s)</small>}</td>
                        <td>{r.emails[0] || '—'}</td>
                        <td>{r.company || '—'}</td>
                        <td>{r.duplicate && <Badge value="doing" label="Duplicado" />}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {Object.keys(summary.rejected_phones).length > 0 && (
                <p className="crm-hint">Números descartados por não serem válidos: {Object.entries(summary.rejected_phones).map(([k, v]) => `${v} (${k})`).join(', ')}. Contatos sem nenhum número ou e-mail válido não são importados.</p>
              )}

              <div className="import-options">
                <div className="field"><label htmlFor="imp-source">Origem dos contatos</label><input id="imp-source" value={options.source} maxLength={100} onChange={(e) => setOptions({ ...options, source: e.target.value })} /></div>
                <div className="field"><label htmlFor="imp-ddd">DDD padrão</label><input id="imp-ddd" inputMode="numeric" maxLength={2} placeholder="Ex.: 66" value={options.default_ddd} onChange={(e) => setOptions({ ...options, default_ddd: e.target.value.replace(/\D/g, '') })} /><small>Aplicado a números sem DDD.</small></div>
                <div className="field"><label htmlFor="imp-dup">Contatos que já existem</label>
                  <select id="imp-dup" value={options.duplicates} onChange={(e) => setOptions({ ...options, duplicates: e.target.value })}>
                    <option value="skip">Ignorar</option><option value="update">Completar dados que faltam</option>
                  </select></div>
              </div>
              <div className="import-checks">
                <label className="checkbox-label"><input type="checkbox" checked={options.create_companies} onChange={(e) => setOptions({ ...options, create_companies: e.target.checked })} />Criar empresas a partir da coluna de empresa</label>
                <label className="checkbox-label"><input type="checkbox" checked={options.import_tags} onChange={(e) => setOptions({ ...options, import_tags: e.target.checked })} />Importar etiquetas como tags</label>
                <label className="checkbox-label"><input type="checkbox" checked={options.trigger_automations} onChange={(e) => setOptions({ ...options, trigger_automations: e.target.checked })} />Disparar automações de “Contato criado” (pode gerar muitas tarefas e mensagens)</label>
              </div>
              {options.import_tags && summary.labels.length > 0 && (
                <div className="field"><label>Etiquetas encontradas <small>(clique para ignorar)</small></label>
                  <div className="import-labels">
                    {summary.labels.map((l) => {
                      const off = (ignored || []).includes(l.label) || l.label.startsWith('*');
                      return <button type="button" key={l.label} className={'deal-chip' + (off ? ' off' : '')} aria-pressed={!off} disabled={l.label.startsWith('*')}
                        onClick={() => setIgnored((cur) => ((cur || []).includes(l.label) ? (cur || []).filter((x) => x !== l.label) : [...(cur || []), l.label]))}>{l.label} · {l.count}</button>;
                    })}
                  </div>
                </div>
              )}

              {preview.format !== 'vcard' && (
                <div className="import-mapping">
                  <button type="button" className="link-btn" onClick={() => setShowMapping(!showMapping)}><SlidersHorizontal size={14} /> {showMapping ? 'Ocultar' : 'Ajustar'} colunas reconhecidas</button>
                  {showMapping && mapping && (
                    <div className="import-map-grid">
                      {Object.entries(preview.field_labels).map(([key, label]) => {
                        const multi = preview.multi.includes(key);
                        const selected = mapping[key] || [];
                        const slots = multi ? [...selected, ''] : [selected[0] || ''];
                        return (
                          <div className="field" key={key}>
                            <label>{label}</label>
                            {slots.map((value, i) => (
                              <select key={i} aria-label={`${label} ${i + 1}`} value={value} onChange={(e) => setMap(key, i, e.target.value)}>
                                <option value="">{multi && i > 0 ? 'Adicionar coluna…' : 'Não importar'}</option>
                                {preview.headers.map((h) => <option key={h} value={h}>{h}</option>)}
                              </select>
                            ))}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          <div className="modal-footer">
            <Button variant="secondary" disabled={running} onClick={onClose}>Cancelar</Button>
            <Button disabled={!preview || running || loading || !summary || summary.valid <= 0 || (options.duplicates === 'skip' && toImport <= 0)} onClick={run}>
              {running ? 'Importando…' : `Importar ${toImport > 0 ? toImport : ''} contato${toImport === 1 ? '' : 's'}`}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
