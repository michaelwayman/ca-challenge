import { applyPatch, DEFAULT_STATE, parseState, serializeState } from './urlState';

describe('parseState', () => {
  it('returns the defaults for an empty query', () => {
    expect(parseState('')).toEqual(DEFAULT_STATE);
  });

  it('reads industries, ordering and page', () => {
    expect(parseState('?industry=telecom&industry=finance&ordering=-review_count&page=3')).toEqual({
      industries: ['finance', 'telecom'],
      ordering: '-review_count',
      page: 3,
    });
  });

  it.each(['?ordering=founded_year', '?ordering=', '?ordering=-name'])(
    'ignores an unknown ordering (%s)',
    (search) => {
      expect(parseState(search).ordering).toBe('name');
    },
  );

  it.each(['?page=0', '?page=-2', '?page=abc', '?page=', '?page=1.5x'])(
    'falls back to page 1 for %s',
    (search) => {
      expect(parseState(search).page).toBe(1);
    },
  );

  it('drops empty and duplicate industries', () => {
    expect(parseState('?industry=&industry=retail&industry=retail').industries).toEqual(['retail']);
  });
});

describe('serializeState', () => {
  it('omits defaults', () => {
    expect(serializeState(DEFAULT_STATE)).toBe('');
  });

  it('writes only what differs, with industries sorted', () => {
    expect(
      serializeState({ industries: ['telecom', 'finance'], ordering: 'average_rating', page: 2 }),
    ).toBe('?industry=finance&industry=telecom&ordering=average_rating&page=2');
  });

  it('round-trips', () => {
    const state = { industries: ['finance'], ordering: '-average_rating' as const, page: 4 };
    expect(parseState(serializeState(state))).toEqual(state);
  });
});

describe('applyPatch', () => {
  const state = { industries: ['retail'], ordering: 'name' as const, page: 3 };

  it('resets the page when the industries change', () => {
    expect(applyPatch(state, { industries: [] }).page).toBe(1);
  });

  it('resets the page when the ordering changes', () => {
    expect(applyPatch(state, { ordering: '-review_count' }).page).toBe(1);
  });

  it('keeps the page when only the page changes', () => {
    expect(applyPatch(state, { page: 4 })).toEqual({ ...state, page: 4 });
  });

  it('honours an explicit page alongside a listing change', () => {
    expect(applyPatch(state, { industries: [], page: 2 }).page).toBe(2);
  });
});
