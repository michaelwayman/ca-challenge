import { pageItems } from './Pagination';

describe('pageItems', () => {
  it('lists every page when there are few', () => {
    expect(pageItems(2, 4)).toEqual([1, 2, 3, 4]);
  });

  it('collapses the middle of a long range', () => {
    expect(pageItems(1, 10)).toEqual([1, 2, 'gap', 10]);
    expect(pageItems(5, 10)).toEqual([1, 'gap', 4, 5, 6, 'gap', 10]);
    expect(pageItems(10, 10)).toEqual([1, 'gap', 9, 10]);
  });

  it('does not add a gap between neighbours of the ends', () => {
    expect(pageItems(3, 10)).toEqual([1, 2, 3, 4, 'gap', 10]);
  });
});
