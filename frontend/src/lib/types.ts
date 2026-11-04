import type { ContactRecord, CompanyRecord, OpportunityRecord, PipelineStageRecord, TaskRecord, ActivityRecord } from './api.generated';

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
export interface Contact extends Entity, Pick<ContactRecord, 'name' | 'email' | 'phone' | 'company_id' | 'owner_id' | 'source' | 'archived'> {
  position?: ContactRecord['position']; notes?: ContactRecord['notes']; tags: string[];
  custom_fields: Record<string, string | number | boolean | null>; company_name?: string | null;
}
export interface Company extends Entity, Pick<CompanyRecord, 'name' | 'email' | 'phone'> { document?: CompanyRecord['document'] }
export interface Pipeline extends Entity { name: string }
export interface PipelineStage extends Entity, Pick<PipelineStageRecord, 'name' | 'color' | 'position' | 'probability' | 'pipeline_id'> {}
export type DealStatus = OpportunityRecord['status'];
export interface Opportunity extends Entity, Pick<OpportunityRecord, 'title' | 'amount' | 'stage_id' | 'contact_id' | 'company_id' | 'owner_id' | 'expected_close_date' | 'description' | 'loss_reason'> {
  status: DealStatus; pipeline_id?: string | null; stage_changed_at?: string | null; last_contact_at?: string | null;
  contact_name?: string | null; contact_phone?: string | null; contact_email?: string | null;
  company_name?: string | null; owner_name?: string | null;
  history?: { id: string; created_at: string; to_stage_id: string }[];
}
export interface Activity extends Entity, Pick<ActivityRecord, 'title' | 'kind' | 'status' | 'scheduled_at' | 'notes' | 'owner_id' | 'contact_id' | 'company_id' | 'opportunity_id'> {}
export interface Task extends Entity, Pick<TaskRecord, 'title' | 'due_date' | 'contact_id' | 'assignee_id' | 'description' | 'status'> {
  priority: string;
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
