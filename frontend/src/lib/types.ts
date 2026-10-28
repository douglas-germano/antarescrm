/** @deprecated Use a domain contract for new API consumers. Legacy configurable UI only. */
export interface Row {
  id: string;
  [key: string]: any;
}
export interface User extends Entity {
  workspace_id: string;
  title?: string | null;
  name: string;
  email: string;
  role: string;
  active: boolean;
}
export interface Workspace extends Entity {
  parent_workspace_id?: string | null;
  name: string;
  slug: string;
  timezone: string;
}
export interface Page<T = Row> {
  items: T[];
  page: number;
  per_page: number;
  pages: number;
  total: number;
}
export type FormData = Record<string, any>;
export interface Option {
  value: string;
  label: string;
}
export interface Field {
  name: string;
  label: string;
  type?:
    | 'text'
    | 'email'
    | 'password'
    | 'textarea'
    | 'number'
    | 'money'
    | 'date'
    | 'datetime-local'
    | 'select'
    | 'contact'
    | 'company'
    | 'checkbox'
    | 'url';
  required?: boolean;
  options?: Option[];
  placeholder?: string;
  wide?: boolean;
  min?: number;
  max?: number;
  help?: string;
  defaultValue?: any;
  emptyValue?: string | null;
}

/** API contracts for the CRM. These do not inherit the permissive legacy Row. */
export interface Entity { id: string; created_at?: string; updated_at?: string }
export interface Contact extends Entity {
  name: string; email: string | null; phone: string | null; company_id: string | null;
  owner_id: string | null; source: string | null; archived: boolean; position?: string | null;
  notes?: string | null; tags: string[]; custom_fields: Record<string, string | number | boolean | null>;
  company_name?: string | null;
}
export interface Company extends Entity { name: string; email: string | null; phone: string | null; document?: string | null }
export interface Pipeline extends Entity { name: string }
export interface PipelineStage extends Entity { name: string; color: string; position: number; probability: number | null; pipeline_id: string | null }
export type DealStatus = 'open' | 'won' | 'lost';
export interface Opportunity extends Entity {
  title: string; status: DealStatus; amount: string; stage_id: string; pipeline_id?: string | null;
  contact_id: string | null; company_id: string | null; owner_id: string | null;
  expected_close_date: string | null; description: string | null; loss_reason: string | null;
  stage_changed_at?: string | null; last_contact_at?: string | null;
  contact_name?: string | null; contact_phone?: string | null; contact_email?: string | null;
  company_name?: string | null; owner_name?: string | null;
  history?: { id: string; created_at: string; to_stage_id: string }[];
}
export interface Activity extends Entity {
  title: string; kind: string; status: string; scheduled_at: string; notes: string | null;
  owner_id: string | null; contact_id: string | null; company_id: string | null; opportunity_id: string | null;
}
export interface Task extends Entity {
  title: string; status: 'todo' | 'doing' | 'done' | 'cancelled'; priority: string; due_date: string | null;
  contact_id: string | null; assignee_id: string | null; description: string | null;
  contact_name?: string | null; assignee_name?: string | null;
}
export interface OpportunityPage extends Page<Opportunity> {
  sources: string[];
  summary: { amount: string; weighted: string; stages: Record<string, { count: number; amount: string }> };
}
export interface ContactPage extends Page<Contact> { sources: string[]; tags: string[] }
export interface OperationsStatus {
  alerts: string[]; jobs: Record<string, number>; outbox: Record<string, number>;
  worker: { online: boolean; dispatch_enabled: boolean; last_seen_at: string | null };
  backup: { last_backup_at: string; restore_verified: boolean; recent: boolean } | null;
  channels: { channel: string; configured: boolean; missing: string[] }[];
}
