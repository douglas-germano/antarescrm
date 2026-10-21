'use client';
import { useEffect, useId, useRef, useState } from 'react';
import { ChevronDown, Loader2, X } from 'lucide-react';
import { api } from '@/lib/api';
import type { Row } from '@/lib/types';

type Kind = 'contacts' | 'companies';
const NOUN: Record<Kind, string> = { contacts: 'contato', companies: 'empresa' };

const detail = (kind: Kind, row: Row) => (kind === 'contacts' ? [row.phone, row.email].filter(Boolean).join(' · ') : [row.document, row.email].filter(Boolean).join(' · '));

/**
 * Searchable picker backed by the API, so it stays fast with thousands of records.
 * Renders a hidden input named `name`, which makes it work inside plain forms and FormDialog.
 */
export function EntitySelect({ kind, name, id, defaultValue = '', required = false, placeholder, onChange }: {
  kind: Kind; name?: string; id?: string; defaultValue?: string | null; required?: boolean; placeholder?: string; onChange?: (id: string, row?: Row) => void;
}) {
  const uid = useId();
  const [value, setValue] = useState(defaultValue || '');
  const [label, setLabel] = useState('');
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<Row[]>([]);
  const [loading, setLoading] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const root = useRef<HTMLDivElement>(null);

  // Show the name of the record that is already selected.
  useEffect(() => {
    let alive = true;
    if (!value) { setLabel(''); return; }
    if (label) return;
    api<Row>(`/${kind}/${value}`).then((row) => { if (alive) setLabel(row.name || ''); }).catch(() => { if (alive) setLabel('Registro selecionado'); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, kind]);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await api<{ items: Row[] }>(`/${kind}?per_page=20&search=${encodeURIComponent(query.trim())}`);
        if (alive) { setResults(data.items); setHighlight(0); }
      } catch { if (alive) setResults([]); }
      finally { if (alive) setLoading(false); }
    }, query ? 200 : 0);
    return () => { alive = false; clearTimeout(timer); };
  }, [open, query, kind]);

  useEffect(() => {
    input.current?.setCustomValidity(required && !value ? `Selecione um ${NOUN[kind]}.` : '');
  }, [required, value, kind]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) { setOpen(false); setQuery(''); } };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  function choose(row?: Row) {
    setValue(row?.id || '');
    setLabel(row?.name || '');
    setQuery('');
    setOpen(false);
    onChange?.(row?.id || '', row);
  }

  return (
    <div className="entity-select" ref={root}>
      {name && <input type="hidden" name={name} value={value} />}
      <div className="entity-control">
        <input ref={input} id={id} role="combobox" aria-expanded={open} aria-controls={uid + '-list'} aria-autocomplete="list" autoComplete="off"
          placeholder={placeholder || `Buscar ${NOUN[kind]} por nome, telefone ou e-mail`}
          value={open ? query : label} onFocus={() => setOpen(true)} onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setHighlight((h) => Math.min(results.length - 1, h + 1)); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setHighlight((h) => Math.max(0, h - 1)); }
            else if (e.key === 'Enter' && open) { e.preventDefault(); if (results[highlight]) choose(results[highlight]); }
            else if (e.key === 'Escape' && open) { e.stopPropagation(); setOpen(false); setQuery(''); }
            else if (e.key === 'Tab') { setOpen(false); setQuery(''); }
          }} />
        {loading ? <Loader2 size={16} className="spin entity-icon" /> : value ? (
          <button type="button" className="entity-icon entity-clear" aria-label={`Limpar ${NOUN[kind]}`} onClick={() => { choose(); input.current?.focus(); }}><X size={15} /></button>
        ) : <ChevronDown size={16} className="entity-icon" />}
      </div>
      {open && (
        <ul className="entity-list" id={uid + '-list'} role="listbox">
          {results.map((row, index) => (
            <li key={row.id} role="option" aria-selected={row.id === value} className={(index === highlight ? 'active ' : '') + (row.id === value ? 'selected' : '')}
              onMouseDown={(e) => { e.preventDefault(); choose(row); }} onMouseEnter={() => setHighlight(index)}>
              <strong>{row.name}</strong>
              {detail(kind, row) && <small>{detail(kind, row)}</small>}
            </li>
          ))}
          {!results.length && !loading && <li className="entity-empty" role="presentation">{query ? `Nenhum ${NOUN[kind]} encontrado para “${query}”.` : `Nenhum ${NOUN[kind]} cadastrado.`}</li>}
        </ul>
      )}
    </div>
  );
}
