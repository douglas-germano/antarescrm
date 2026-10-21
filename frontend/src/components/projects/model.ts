export const STATUS: Record<string, { label: string; badge: string }> = {
  active: { label: 'Em andamento', badge: 'doing' },
  done: { label: 'Concluído', badge: 'completed' },
  cancelled: { label: 'Cancelado', badge: 'skipped' },
};

export const APPROVAL: Record<string, { label: string; badge: string }> = {
  pending: { label: 'Aguardando', badge: 'doing' },
  approved: { label: 'Aprovado', badge: 'completed' },
  changes_requested: { label: 'Ajustes solicitados', badge: 'lost' },
  cancelled: { label: 'Cancelada', badge: 'skipped' },
  expired: { label: 'Expirada', badge: 'skipped' },
};

export const FILE_KINDS: Record<string, string> = { layout: 'Criativo', document: 'Documento', other: 'Outro' };

export const fileSize = (bytes: number) => (bytes >= 1048576 ? (bytes / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(bytes / 1024)) + ' KB');

/** Download/preview URL of a stored file, served through the authenticated gateway. */
export const fileUrl = (projectId: string, fileId: string, inline = false) => `/api/backend/projects/${projectId}/files/${fileId}/download${inline ? '?inline=1' : ''}`;
