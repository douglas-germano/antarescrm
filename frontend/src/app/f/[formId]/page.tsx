'use client';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { DataState } from '@/components/ui';
import { FormPage } from '@/components/forms/form-view';
import { DEFAULT_DESIGN, type PublicForm } from '@/components/forms/types';

export default function CapturePage() {
  const { formId } = useParams<{ formId: string }>();
  const [form, setForm] = useState<PublicForm | null>(null);
  const [error, setError] = useState<Error>();
  useEffect(() => {
    const controller = new AbortController();
    setForm(null); setError(undefined);
    fetch('/api/public/forms/' + formId, { signal: controller.signal, cache: 'no-store' })
      .then(async (r) => { const body = await r.json(); if (!r.ok) throw new Error(body?.error?.message || 'Formulário indisponível.'); return body; })
      .then(setForm).catch((e) => { if (e.name !== 'AbortError') setError(e); });
    return () => controller.abort();
  }, [formId]);
  if (form) return <FormPage form={form} />;
  return <main className="fv-page fv-card-layout" style={{ background: DEFAULT_DESIGN.background }}><section className="fv-card"><DataState loading={!error} error={error}><span /></DataState></section></main>;
}
