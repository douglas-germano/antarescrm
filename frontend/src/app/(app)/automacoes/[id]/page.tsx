'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { Workflow } from 'lucide-react';
import { useData, useList } from '@/lib/api';
import { useSession } from '@/components/providers';
import { DataState, EmptyState } from '@/components/ui';
import { Card } from '@/components/blocks';
import { emptyConditions } from '@/components/automations/conditions-editor';
import { FlowEditor, type FlowDraft } from '@/components/automations/FlowEditor';
import { RECIPES, stepsOf } from '@/components/automations/model';
import type { Row } from '@/lib/types';

const blank = (): FlowDraft => ({
  name: '', event: 'contact.created', source: '', required_tag: '', assignee_id: '', active: false, stop_on_reply: false,
  conditions: emptyConditions(), steps: [],
});

function fromRule(rule: Row, copy = false): FlowDraft {
  return {
    id: copy ? undefined : rule.id,
    name: copy ? rule.name + ' (cópia)' : rule.name,
    event: rule.event,
    source: rule.source || '',
    required_tag: rule.required_tag || '',
    assignee_id: rule.assignee_id || '',
    active: copy ? false : rule.active,
    stop_on_reply: rule.stop_on_reply || false,
    conditions: { ...emptyConditions(), ...rule.conditions },
    steps: stepsOf(rule),
  };
}

/** /automacoes/nova starts blank, from a recipe (?modelo=N) or as a copy (?copiar=ID); any other id edits that rule. */
export default function AutomationEditorPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useSession();
  const manage = ['owner', 'admin'].includes(user?.role || '');
  const rules = useList('/automations');
  const staff = useList('/users');
  const templates = useList('/message-templates');
  const stages = useData<{ items: Row[] }>('/pipeline/stages');
  const [query, setQuery] = useState<URLSearchParams | null>(null);
  useEffect(() => setQuery(new URLSearchParams(window.location.search)), []);

  if (!manage) return <div className="page"><Card><EmptyState icon={<Workflow />} title="Acesso restrito" description="Somente administradores podem editar automações." /></Card></div>;
  return (
    <DataState loading={rules.isLoading || !query} error={rules.error}>
      {(() => {
        let initial: FlowDraft | null = null;
        if (id === 'nova') {
          const recipe = RECIPES[Number(query?.get('modelo'))];
          const source = (rules.data || []).find((r) => r.id === query?.get('copiar'));
          initial = source ? fromRule(source, true)
            : recipe ? { ...blank(), name: recipe.name, event: recipe.event, steps: recipe.steps, conditions: { ...emptyConditions(), ...recipe.conditions } }
            : blank();
        } else {
          const rule = (rules.data || []).find((r) => r.id === id);
          if (rule) initial = fromRule(rule);
        }
        if (!initial) return <div className="page"><Card><EmptyState icon={<Workflow />} title="Automação não encontrada" description="Ela pode ter sido excluída." action={<Link className="btn btn-primary" href="/automacoes">Ver automações</Link>} /></Card></div>;
        return <FlowEditor key={initial.id || 'nova'} initial={initial} staff={staff.data || []} templates={templates.data || []} stages={stages.data?.items || []} />;
      })()}
    </DataState>
  );
}
