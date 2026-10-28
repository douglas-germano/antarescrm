'use client';
import { useEffect } from 'react';

// Forms with unsaved edits, by id. Switching settings section asks first; closing or reloading the tab warns.
const dirty = new Set<string>();

export function useUnsavedGuard(id: string, isDirty: boolean) {
  useEffect(() => {
    if (isDirty) dirty.add(id);
    else dirty.delete(id);
    return () => { dirty.delete(id); };
  }, [id, isDirty]);
  useEffect(() => {
    if (!isDirty) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [isDirty]);
}

export const confirmLeave = () => !dirty.size || window.confirm('Há alterações não salvas nesta seção. Sair mesmo assim?');
