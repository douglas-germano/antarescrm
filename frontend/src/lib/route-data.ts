import { createIsomorphicFn } from '@tanstack/react-start';
import { prepareData } from './api';
import { pagePath } from './pagination';

const prepared = new Set<string>();
type Plan = { data?: string[]; lists?: string[] };

function planFor(pathname: string): Plan | undefined {
  switch (pathname) {
    case '/': return { data: ['/dashboard'] };
    case '/tarefas': return { data: [pagePath('/tasks?' + new URLSearchParams({ mine: 'false', view: 'open', search: '', priority: '' }), 1, 25)] };
    case '/campanhas': return { data: [pagePath('/campaigns', 1, 25)] };
    case '/empresas': return { lists: ['/companies?archived=false'] };
    case '/projetos': return { data: ['/project-stages'], lists: ['/projects?per_page=100'] };
    case '/funis': return { lists: ['/funnels'] };
    case '/formularios': return { lists: ['/forms'] };
    case '/automacoes': return { lists: ['/automations'] };
    case '/contatos': return { data: [pagePath('/contacts?' + new URLSearchParams({ archived: 'false', search: '', owner_id: '', company_id: '', source: '', has_email: '', tag: '' }), 1, 25)] };
    case '/crm': return { data: ['/pipelines', '/pipeline/stages?pipeline_id=default', pagePath('/opportunities?' + new URLSearchParams({ status: 'open', pipeline_id: 'default', search: '', owner_id: '', source: '', period: '', min_amount: '', max_amount: '', attention: 'false', sort: 'stale', direction: 'desc' }), 1, 25)] };
  }
  const detail = pathname.match(/^\/(projetos|funis|formularios)\/([^/]+)$/);
  if (detail) {
    const resource = { projetos: 'projects', funis: 'funnels', formularios: 'forms' }[detail[1]];
    return { data: [`/${resource}/${detail[2]}`] };
  }
}

/** SSR leaves data loading to the existing screens. Browser navigations can warm their SWR cache. */
export const prepareRoute = createIsomorphicFn()
  .server(async (_pathname: string) => {})
  .client(async (pathname: string) => {
    if (prepared.has(pathname)) return; // Subsequent visits use SWR's cached data and background revalidation.
    const plan = planFor(pathname);
    if (!plan) return;
    try {
      await prepareData(plan);
      prepared.add(pathname);
    } catch { /* The destination screen presents request errors with its existing retry controls. */ }
  });
