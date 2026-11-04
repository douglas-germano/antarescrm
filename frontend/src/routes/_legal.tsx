import { createFileRoute, Outlet } from '@tanstack/react-router';
import LegalLayout from '@/components/layout/legal-layout';

export const Route = createFileRoute('/_legal')({
  component: () => <LegalLayout><Outlet /></LegalLayout>,
});
