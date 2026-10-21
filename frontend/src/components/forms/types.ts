export type FieldType =
  | 'text' | 'textarea' | 'number' | 'date' | 'select' | 'checkbox' | 'email' | 'phone' | 'url'
  | 'radio' | 'multiselect' | 'heading' | 'paragraph' | 'divider';

export type Answer = string | boolean | string[];
export type CaptureField = {
  key: string;
  label: string;
  type: FieldType;
  required: boolean;
  options: string[];
  placeholder?: string;
  help_text?: string;
  width?: 'full' | 'half';
  map_to?: string;
  show_if?: { field: string; equals: string | boolean };
};
export type FormDesign = {
  background: string; card_color: string; text_color: string; font: 'sans' | 'serif' | 'mono' | 'rounded';
  radius: number; align: 'left' | 'center'; max_width: number; layout: 'card' | 'plain';
  button_label: string; button_style: 'pill' | 'rounded' | 'square'; button_width: 'auto' | 'full';
  logo_url: string; show_brand: boolean;
};
export type BaseFieldConfig = { label?: string; placeholder?: string; visible?: boolean; required?: boolean };
export type BaseFields = { name?: BaseFieldConfig; email?: BaseFieldConfig; phone?: BaseFieldConfig };
export type FormSettings = {
  consent_text?: string;
  base_fields?: BaseFields;
  after_submit?: { type: 'message' | 'redirect'; url: string };
};
export type PublicForm = {
  id: string; headline: string; description: string; consent_text: string; fields: CaptureField[];
  brand_name: string; accent_color: string; design: FormDesign; base_fields: BaseFields;
};

export const DEFAULT_DESIGN: FormDesign = {
  background: '#f2f2f2', card_color: '#ffffff', text_color: '#25282b', font: 'sans', radius: 6, align: 'left',
  max_width: 520, layout: 'card', button_label: 'Enviar solicitação', button_style: 'pill', button_width: 'auto',
  logo_url: '', show_brand: true,
};

export const FIELD_TYPES: { value: FieldType; label: string; group: 'input' | 'choice' | 'layout' }[] = [
  { value: 'text', label: 'Texto curto', group: 'input' },
  { value: 'textarea', label: 'Texto longo', group: 'input' },
  { value: 'email', label: 'E-mail', group: 'input' },
  { value: 'phone', label: 'Telefone', group: 'input' },
  { value: 'url', label: 'Link', group: 'input' },
  { value: 'number', label: 'Número', group: 'input' },
  { value: 'date', label: 'Data', group: 'input' },
  { value: 'select', label: 'Lista suspensa', group: 'choice' },
  { value: 'radio', label: 'Escolha única', group: 'choice' },
  { value: 'multiselect', label: 'Múltipla escolha', group: 'choice' },
  { value: 'checkbox', label: 'Caixa de seleção', group: 'choice' },
  { value: 'heading', label: 'Título', group: 'layout' },
  { value: 'paragraph', label: 'Texto explicativo', group: 'layout' },
  { value: 'divider', label: 'Divisória', group: 'layout' },
];
export const typeLabel = (type: string) => FIELD_TYPES.find((t) => t.value === type)?.label || type;
export const hasOptions = (type: string) => ['select', 'radio', 'multiselect'].includes(type);
export const isLayout = (type: string) => ['heading', 'paragraph', 'divider'].includes(type);

export const DEFAULT_CONSENT = 'Autorizo o contato em resposta a esta solicitação.';

/** Builds the visitor-facing payload from a stored form so the editor can preview it without a request. */
export function toPublicForm(row: Record<string, any>): PublicForm {
  return {
    id: row.id, headline: row.headline, description: row.description || '', consent_text: row.settings?.consent_text || DEFAULT_CONSENT,
    fields: row.fields || [], brand_name: row.brand_name || '', accent_color: row.accent_color,
    design: { ...DEFAULT_DESIGN, ...row.design }, base_fields: row.settings?.base_fields || {},
  };
}
