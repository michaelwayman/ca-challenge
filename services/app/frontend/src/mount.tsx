import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import type { Industry } from './api';
import { BrandList } from './components/brand-list/BrandList';

/** Mounts <BrandList /> into `element`. The host page supplies its configuration:
 *  data-api-url, data-page-size, and the industries as a JSON <script> whose id is
 *  in data-industries-id. */
export function mountBrandList(element: HTMLElement) {
  const industriesScript = document.getElementById(element.dataset.industriesId ?? '');
  const industries = JSON.parse(industriesScript?.textContent ?? '[]') as Industry[];
  const pageSize = Number(element.dataset.pageSize) || undefined;

  createRoot(element).render(
    <StrictMode>
      <QueryClientProvider client={new QueryClient()}>
        <BrandList industries={industries} apiUrl={element.dataset.apiUrl} pageSize={pageSize} />
      </QueryClientProvider>
    </StrictMode>,
  );
}
