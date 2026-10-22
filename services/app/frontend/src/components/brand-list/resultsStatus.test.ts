import { resultsStatus } from './resultsStatus';

const base = { loading: false, updating: false, page: 1, pageSize: 12, total: 40, shown: 12 };

describe('resultsStatus', () => {
  it('describes the range on the first page', () => {
    expect(resultsStatus(base)).toBe('Showing 1–12 of 40 brands');
  });

  it('describes a later, shorter page', () => {
    expect(resultsStatus({ ...base, page: 4, shown: 4 })).toBe('Showing 37–40 of 40 brands');
  });

  it('uses the singular for one brand', () => {
    expect(resultsStatus({ ...base, total: 1, shown: 1 })).toBe('Showing 1–1 of 1 brand');
  });

  it('says so when nothing matches', () => {
    expect(resultsStatus({ ...base, total: 0, shown: 0 })).toBe('No brands found.');
  });

  it('reports loading and updating before anything else', () => {
    expect(resultsStatus({ ...base, loading: true })).toBe('Loading brands…');
    expect(resultsStatus({ ...base, updating: true })).toBe('Updating results…');
  });

  it('is empty before the first response', () => {
    expect(resultsStatus({ ...base, total: undefined, shown: 0 })).toBe('');
  });
});
