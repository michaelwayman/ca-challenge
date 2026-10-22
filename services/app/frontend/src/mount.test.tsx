import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { jsonResponse, makeBrand, makePage } from './test-utils';
import { mountBrandList } from './mount';

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

it('configures the component from the host page', async () => {
  // A fresh Response per call: a body can only be read once, and StrictMode may fetch twice.
  const fetchMock = vi
    .fn()
    .mockImplementation(() => Promise.resolve(jsonResponse(makePage([makeBrand('acme')]))));
  vi.stubGlobal('fetch', fetchMock);
  document.body.innerHTML = `
    <script type="application/json" id="industries">[{"name":"Retail","slug":"retail"}]</script>
    <div id="mount" data-api-url="/custom/brands/" data-page-size="6" data-industries-id="industries"></div>`;

  mountBrandList(document.getElementById('mount')!);

  expect(await screen.findByRole('heading', { name: 'Acme' })).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /^Industry/ }));
  expect(screen.getByRole('checkbox', { name: 'Retail' })).toBeInTheDocument();
  expect(fetchMock.mock.calls[0]![0]).toBe('/custom/brands/?page_size=6');
});
