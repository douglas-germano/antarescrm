'use client';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { DataState } from '@/components/ui';
import { PageRenderer } from '@/components/funnels/page-renderer';
import type { PublicForm } from '@/components/forms/types';
import type { Block, StepSettings, Theme } from '@/components/funnels/types';

type PublicPage = {
  funnel: { id: string; name: string; theme: Theme };
  step: { id: string; slug: string; name: string; settings: StepSettings; blocks: Block[] };
  next_slug: string | null;
  forms: Record<string, PublicForm>;
};
const VISITOR_KEY = 'antares:visitor';

function visitorId(): string {
  try {
    const stored = localStorage.getItem(VISITOR_KEY);
    if (stored && /^[0-9a-f-]{36}$/i.test(stored)) return stored;
    const created = crypto.randomUUID();
    localStorage.setItem(VISITOR_KEY, created);
    return created;
  } catch { return crypto.randomUUID(); }
}

export default function FunnelPublicPage() {
  const { funnelId, slug } = useParams<{ funnelId: string; slug?: string[] }>();
  const router = useRouter();
  const step = slug?.[0] || '';
  const [page, setPage] = useState<PublicPage | null>(null);
  const [error, setError] = useState<Error>();
  const visitor = useMemo(() => (typeof window === 'undefined' ? '' : visitorId()), []);

  useEffect(() => {
    const controller = new AbortController();
    setPage(null); setError(undefined);
    fetch(`/api/public/funnels/${funnelId}${step ? '/' + encodeURIComponent(step) : ''}`, { signal: controller.signal, cache: 'no-store' })
      .then(async (r) => { const body = await r.json(); if (!r.ok) throw new Error(body?.error?.message || 'Página indisponível.'); return body as PublicPage; })
      .then((body) => {
        setPage(body);
        document.title = body.step.settings.title || body.step.name;
        document.querySelector('meta[name="description"]')?.setAttribute('content', body.step.settings.description || '');
        fetch(`/api/public/funnels/${funnelId}/steps/${body.step.id}/view`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ visitor_id: visitor }), keepalive: true }).catch(() => undefined);
      })
      .catch((e) => { if (e.name !== 'AbortError') setError(e); });
    return () => controller.abort();
  }, [funnelId, step, visitor]);

  if (!page) return <main className="fp-status"><DataState loading={!error} error={error}><span /></DataState></main>;
  const next = () => {
    if (!page.next_slug) return;
    router.push(`/p/${funnelId}/${page.next_slug}${window.location.search}`);
    window.scrollTo({ top: 0 });
  };
  return <PageRenderer key={page.step.id} blocks={page.step.blocks} theme={page.funnel.theme} settings={page.step.settings} forms={page.forms} mode="live" onNext={next} funnelId={funnelId}
    attribution={{ funnel_id: funnelId, funnel_step_id: page.step.id, visitor_id: visitor }} />;
}
