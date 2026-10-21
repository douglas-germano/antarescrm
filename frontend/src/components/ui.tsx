'use client';
import { useEffect, useRef, useState, useId, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { Loader2, Search, X, FolderOpen, ArrowUpRight, AlertCircle } from 'lucide-react';
import { statuses, priorities } from '@/lib/format';
import type { Field, FormData } from '@/lib/types';
import { EntitySelect } from './entity-select';

export function Button({
  variant = 'primary',
  className = '',
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger' }) {
  return (
    <button type="button" {...props} className={`btn btn-${variant} ${className}`}>
      {children}
    </button>
  );
}
export function Badge({ value, label }: { value: string; label?: string }) {
  return (
    <span className={'badge badge-' + value}>
      <span className="badge-dot" />
      {label || statuses[value] || priorities[value] || value}
    </span>
  );
}
export function PageHeader({
  eyebrow,
  title,
  description,
  children,
  compact = false,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  children?: ReactNode;
  compact?: boolean;
}) {
  return (
    <header className={'page-header' + (compact ? ' compact-header' : '')}>
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      <div className="header-actions">{children}</div>
    </header>
  );
}
export function StatCard({
  label,
  value,
  detail,
  icon,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="stat-card">
      <div className="stat-top">
        <span>{label}</span>
        {icon && <span className="stat-icon">{icon}</span>}
      </div>
      <strong className="stat-value">{value}</strong>
      {detail && <span className="stat-detail">{detail}</span>}
    </div>
  );
}
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon || <FolderOpen size={26} />}</div>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}
export function DataState({
  loading,
  error,
  children,
}: {
  loading: boolean;
  error?: any;
  children: ReactNode;
}) {
  if (loading)
    return (
      <div className="loading-state" role="status">
        <Loader2 className="spin" size={22} />
        <span>Carregando…</span>
      </div>
    );
  if (error)
    return (
      <div className="error-panel" role="alert">
        <AlertCircle size={20} />
        <div>
          <strong>Não foi possível carregar os dados</strong>
          <p>{error.message || 'Tente novamente em instantes.'}</p>
          <Button variant="secondary" onClick={() => window.location.reload()}>
            Tentar novamente
          </Button>
        </div>
      </div>
    );
  return <>{children}</>;
}
export function SearchInput({
  value,
  onChange,
  placeholder = 'Buscar…',
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="search">
      <Search size={17} />
      <input
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button aria-label="Limpar busca" onClick={() => onChange('')}>
          <X size={15} />
        </button>
      )}
    </div>
  );
}
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  wide = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  wide?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const el = dialog.current;
    if (open && !el?.open) el?.showModal();
    if (!open && el?.open) el.close();
  }, [open]);
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = '';
      };
    }
  }, [open]);
  return (
    <dialog
      ref={dialog}
      className={'modal ' + (wide ? 'modal-wide' : '')}
      aria-labelledby={id}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === dialog.current) {
          const r = dialog.current.getBoundingClientRect();
          if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom)
            onClose();
        }
      }}
    >
      <div className="modal-header">
        <div>
          <h2 id={id}>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        <button className="icon-btn" aria-label="Fechar janela" onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      {open && <div className="modal-content">{children}</div>}
    </dialog>
  );
}
export function FormDialog({
  open,
  onClose,
  title,
  description,
  fields,
  initial = {},
  onSubmit,
  submitLabel = 'Salvar',
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  fields: Field[];
  initial?: FormData;
  onSubmit: (data: FormData) => Promise<void>;
  submitLabel?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const id = useId();
  useEffect(() => {
    if (open) setError('');
  }, [open]);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    const raw = new globalThis.FormData(event.currentTarget);
    const result: FormData = {};
    for (const field of fields) {
      const value = raw.get(field.name);
      if (field.type === 'checkbox') {
        result[field.name] = value === 'on';
        continue;
      }
      if (value === null || value === '') {
        if (field.emptyValue !== undefined) { result[field.name] = field.emptyValue; continue; }
        if (
          !field.required &&
          initial[field.name] &&
          [
            'assignee_id',
            'owner_id',
            'company_id',
            'contact_id',
            'opportunity_id',
            'due_date',
            'expected_close_date',
            'description',
            'address',
            'notes',
            'email',
            'phone',
            'source',
            'document',
            'position',
            'website',
            'industry',
          ].includes(field.name)
        )
          result[field.name] = null;
        continue;
      }
      result[field.name] =
        field.type === 'number'
          ? Number(value)
          : field.type === 'datetime-local'
            ? new Date(String(value)).toISOString()
            : field.type === 'money'
              ? String(value).replace(',', '.')
              : String(value).trim();
    }
    try {
      await onSubmit(result);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Não foi possível salvar.');
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      open={open}
      onClose={() => {
        if (!busy) onClose();
      }}
      title={title}
      description={description}
    >
      <form onSubmit={submit}>
        <fieldset disabled={busy} className="form-grid">
          {fields.map((field) => {
            const htmlId = id + '-' + field.name;
            const value = initial[field.name] ?? field.defaultValue ?? '';
            return (
              <div
                className={'field ' + (field.wide || field.type === 'textarea' ? 'field-wide' : '')}
                key={field.name}
              >
                {field.type === 'checkbox' ? (
                  <label className="checkbox-label">
                    <input type="checkbox" name={field.name} defaultChecked={Boolean(value)} />
                    {field.label}
                  </label>
                ) : (
                  <>
                    <label htmlFor={htmlId}>
                      {field.label}
                      {field.required && <span className="required"> *</span>}
                    </label>
                    {field.type === 'contact' || field.type === 'company' ? (
                      <EntitySelect kind={field.type === 'contact' ? 'contacts' : 'companies'} name={field.name} id={htmlId} required={field.required} defaultValue={value} />
                    ) : field.type === 'select' ? (
                      <select name={field.name} id={htmlId} required={field.required} defaultValue={value}>
                        <option value="">Selecione…</option>
                        {field.options?.map((option) => (
                          <option value={option.value} key={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    ) : field.type === 'textarea' ? (
                      <textarea
                        id={htmlId}
                        name={field.name}
                        defaultValue={value}
                        placeholder={field.placeholder}
                        required={field.required}
                        rows={3}
                      />
                    ) : (
                      <input
                        id={htmlId}
                        name={field.name}
                        type={field.type === 'money' ? 'number' : field.type || 'text'}
                        defaultValue={
                          field.type === 'datetime-local' && value ? String(value).slice(0, 16) : value
                        }
                        placeholder={field.placeholder}
                        required={field.required}
                        min={field.min ?? (field.type === 'money' ? 0 : undefined)}
                        max={field.max}
                        step={field.type === 'money' ? '0.01' : field.type === 'number' ? '1' : undefined}
                        autoComplete={field.type === 'password' ? 'new-password' : undefined}
                      />
                    )}
                  </>
                )}
                {field.help && <small>{field.help}</small>}
              </div>
            );
          })}
        </fieldset>
        {error && (
          <div className="form-error" role="alert">
            <AlertCircle size={17} />
            {error}
          </div>
        )}
        <div className="modal-footer">
          <Button variant="secondary" disabled={busy} onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" disabled={busy}>
            {busy && <Loader2 className="spin" size={16} />} {busy ? 'Salvando…' : submitLabel}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
export function ConfirmDialog({
  open,
  onClose,
  title,
  description,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description: string;
  onConfirm: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => setError(''), [open]);
  return (
    <Modal
      open={open}
      onClose={() => {
        if (!busy) onClose();
      }}
      title={title}
      description={description}
    >
      {error && <div className="form-error">{error}</div>}
      <div className="modal-footer">
        <Button variant="secondary" disabled={busy} onClick={onClose}>
          Cancelar
        </Button>
        <Button
          variant="danger"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onConfirm();
              onClose();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? 'Aguarde…' : 'Confirmar'}
        </Button>
      </div>
    </Modal>
  );
}
