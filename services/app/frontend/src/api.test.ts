import { ApiError, buildQuery, fetchBrands, shouldRetry } from './api';
import { DEFAULT_STATE } from './urlState';

describe('buildQuery', () => {
  it('always sends the page size and omits defaults', () => {
    expect(buildQuery(DEFAULT_STATE, 12)).toBe('page_size=12');
  });

  it('repeats industry and passes ordering and page through', () => {
    const state = {
      industries: ['finance', 'telecom'],
      ordering: '-review_count' as const,
      page: 2,
    };
    expect(buildQuery(state, 12)).toBe(
      'industry=finance&industry=telecom&ordering=-review_count&page=2&page_size=12',
    );
  });
});

describe('fetchBrands', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('requests the API and returns the parsed page', async () => {
    const page = { count: 0, next: null, previous: null, results: [] };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(page)));
    vi.stubGlobal('fetch', fetchMock);
    const controller = new AbortController();

    const result = await fetchBrands('/api/brands/', DEFAULT_STATE, 12, controller.signal);

    expect(result).toEqual(page);
    expect(fetchMock).toHaveBeenCalledWith('/api/brands/?page_size=12', {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    });
  });

  it('throws an ApiError carrying the status for a failed response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('nope', { status: 404 })));

    await expect(fetchBrands('/api/brands/', DEFAULT_STATE, 12)).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
    });
  });
});

describe('shouldRetry', () => {
  it('retries network errors and server errors up to twice', () => {
    expect(shouldRetry(0, new TypeError('Failed to fetch'))).toBe(true);
    expect(shouldRetry(1, new ApiError(503, 'x'))).toBe(true);
    expect(shouldRetry(2, new ApiError(503, 'x'))).toBe(false);
  });

  it('never retries a client error', () => {
    expect(shouldRetry(0, new ApiError(404, 'x'))).toBe(false);
    expect(shouldRetry(0, new ApiError(400, 'x'))).toBe(false);
  });
});
