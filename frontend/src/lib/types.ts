export interface Row {
  id: string;
  [key: string]: any;
}
export interface User extends Row {
  name: string;
  email: string;
  role: string;
  active: boolean;
}
export interface Workspace extends Row {
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
