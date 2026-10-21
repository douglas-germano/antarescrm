'use client';
import { useData } from '@/lib/api';
import { Button } from '@/components/ui';
export type Conditions = { mode: 'all' | 'any'; items: { field: string; operator: string; value: string }[] };
export const emptyConditions = (): Conditions => ({ mode:'all', items:[] });
export function ConditionsEditor({ value, onChange, label = 'Condições adicionais' }: { value: Conditions; onChange: (value: Conditions) => void; label?: string }) {
  const stages = useData('/pipeline/stages');
  const update = (index: number, patch: Partial<Conditions['items'][0]>) => onChange({ ...value, items: value.items.map((item,i) => i === index ? { ...item,...patch }:item) });
  return <section className="stack"><h3>{label}</h3>{!!value.items.length && <label>Aplicar quando<select value={value.mode} onChange={e => onChange({ ...value, mode:e.target.value as Conditions['mode'] })}><option value="all">Todas as condições forem atendidas</option><option value="any">Pelo menos uma condição for atendida</option></select></label>}
    {value.items.map((item,i) => <div className="form-grid" key={i}><label>Campo<select value={item.field.startsWith('custom.') ? 'custom':item.field} onChange={e => update(i,{ field:e.target.value === 'custom' ? 'custom.':e.target.value })}>{[['source','Origem'],['name','Nome'],['email','E-mail'],['phone','Telefone'],['tag','Tag'],['deal.stage_id','Etapa do negócio'],['deal.status','Estado do negócio'],['deal.amount','Valor do negócio'],['comment.text','Texto do comentário (Instagram)'],['comment.media_id','Publicação (ID) do comentário'],['custom','Campo personalizado']].map(([v,l]) => <option value={v} key={v}>{l}</option>)}</select></label>
      {item.field.startsWith('custom.') && <label>Identificador do campo<input required pattern="[a-z][a-z0-9_]{0,39}" maxLength={40} value={item.field.slice(7)} onChange={e => update(i,{ field:'custom.' + e.target.value })} /></label>}
      <label>Comparação<select value={item.operator} onChange={e => update(i,{ operator:e.target.value })}>{[['equals','É igual a'],['not_equals','É diferente de'],['contains','Contém'],['exists','Está preenchido'],['gte','É maior ou igual a'],['lt','É menor que']].map(([v,l]) => <option value={v} key={v}>{l}</option>)}</select></label>
      {item.operator !== 'exists' && (item.field === 'deal.stage_id' ? <label>Etapa<select required value={item.value} onChange={e => update(i,{ value:e.target.value })}><option value="">Selecione…</option>{stages.data?.items.map((stage: any) => <option key={stage.id} value={stage.id}>{stage.pipeline_name} · {stage.name}</option>)}</select></label> : item.field === 'deal.status' ? <label>Estado<select required value={item.value} onChange={e => update(i,{ value:e.target.value })}><option value="">Selecione…</option><option value="open">Em aberto</option><option value="won">Ganho</option><option value="lost">Perdido</option></select></label> : <label>Valor<input required maxLength={2000} value={item.value} onChange={e => update(i,{ value:e.target.value })} /></label>)}
      <Button variant="ghost" aria-label={'Remover condição ' + (i+1)} onClick={() => onChange({ ...value, items:value.items.filter((_,j) => j !== i) })}>Remover condição</Button>
    </div>)}
    <Button variant="secondary" disabled={value.items.length >= 10} onClick={() => onChange({ ...value, items:[...value.items,{ field:'source',operator:'equals',value:'' }] })}>Adicionar condição</Button>
  </section>;
}
