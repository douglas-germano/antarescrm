'use client';
import { Button } from '@/components/ui';
export type Availability = Record<string, { start: string; end: string }[]>;
export function AvailabilityEditor({ value, onChange }: { value: Availability; onChange: (value: Availability) => void }) {
  return <div className="stack">{['Segunda','Terça','Quarta','Quinta','Sexta','Sábado','Domingo'].map((label,index) => {
    const key = String(index), windows = value[key] || [];
    return <section className="availability-day" key={key}><label className="checkbox-label"><input type="checkbox" checked={windows.length > 0} onChange={e => onChange({ ...value, [key]: e.target.checked ? [{ start: '09:00', end: '18:00' }] : [] })} />{label}</label>
      {windows.map((window,i) => <div className="availability-window" key={i}><label>Das<input aria-label={label + ' início ' + (i+1)} type="time" required value={window.start} onChange={e => onChange({ ...value, [key]: windows.map((w,j) => j === i ? { ...w, start: e.target.value } : w) })} /></label><label>Até<input aria-label={label + ' fim ' + (i+1)} type="time" required value={window.end} onChange={e => onChange({ ...value, [key]: windows.map((w,j) => j === i ? { ...w, end: e.target.value } : w) })} /></label><Button variant="ghost" aria-label={'Remover intervalo de ' + label} onClick={() => onChange({ ...value, [key]: windows.filter((_,j) => j !== i) })}>Remover</Button></div>)}
      {!!windows.length && windows.length < 4 && <Button variant="ghost" onClick={() => onChange({ ...value, [key]: [...windows, { start: '19:00', end: '20:00' }] })}>Adicionar intervalo</Button>}
    </section>;
  })}</div>;
}
