export type FishingSettings = {
  enabled: boolean; provider_ready: boolean; brand_name: string; brand_profile: string;
  tone: string; examples: string; allowed_topics: string; forbidden_words: string[];
  blocked_authors: string[]; own_username: string; objective: string;
  score_threshold: number; daily_limit: number; daily_ai_limit: number;
};
export type FishingDraft = { id: string; kind: string; text: string };
export type FishingPost = {
  id: string; url: string; caption: string; author: string; status: string;
  score: number | null; reason: string | null; summary: string | null; error: string | null;
  has_image: boolean; opened_at: string | null; user_id: string; published_text: string | null;
  created_at: string; drafts: FishingDraft[];
};
export type FishingMetrics = {
  counts: Record<string, number>; total: number; published_today: number; edit_rate: number;
  approval_rate: number; tokens: number; cost_usd: string | null; unknown_cost_calls: number; ai_calls_today: number;
};
export const statusLabels: Record<string, string> = {
  na_fila: 'Para revisar', novo: 'Aguardando IA', processando: 'Analisando', publicado: 'Publicados',
  pulado: 'Pulados', descartado: 'Descartados', expirado: 'Expirados', erro: 'Falhas', todos: 'Todos',
};
