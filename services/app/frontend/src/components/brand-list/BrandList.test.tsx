import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';

import type { Industry } from '../../api';
import {
  deferred,
  INDUSTRIES,
  jsonResponse,
  makeBrand,
  makePage,
  renderWithClient,
} from '../../test-utils';
import { BrandList } from './BrandList';

const fetchMock = vi.fn();

beforeEach(() => {
  window.history.replaceState(null, '', '/brand/');
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const requestedUrls = () => fetchMock.mock.calls.map(([url]) => url as string);
const lastUrl = () => requestedUrls().at(-1)!;
const renderList = (industries: Industry[] = INDUSTRIES) =>
  renderWithClient(<BrandList industries={industries} />);

type User = ReturnType<typeof userEvent.setup>;
const industryButton = () => screen.getByRole('button', { name: /^Industry/ });
const sortButton = () => screen.getByRole('button', { name: /^Sort by/ });
const checkbox = (name: string) => screen.getByRole('checkbox', { name });

async function openIndustries(user: User) {
  await user.click(industryButton());
  return screen.getByRole('group', { name: 'Industry' });
}

const tagList = () => screen.queryByRole('list', { name: 'Active industry filters' });

function respondWith(...pages: ReturnType<typeof makePage>[]) {
  pages.forEach((page) => fetchMock.mockResolvedValueOnce(jsonResponse(page)));
}

describe('loading and results', () => {
  it('shows skeletons while loading, then the brand cards', async () => {
    const pending = deferred<Response>();
    fetchMock.mockReturnValueOnce(pending.promise);

    renderList();

    expect(screen.getByTestId('card-skeleton')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Loading brands');

    pending.resolve(jsonResponse(makePage([makeBrand('acme'), makeBrand('urban')])));

    expect(await screen.findByRole('heading', { name: 'Acme', level: 3 })).toBeInTheDocument();
    expect(screen.queryByTestId('card-skeleton')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Showing 1–2 of 2 brands');
  });

  it('renders everything a card needs, including the top review snippet', async () => {
    respondWith(makePage([makeBrand('acme')]));

    renderList();

    const card = (await screen.findByRole('heading', { name: 'Acme' })).closest('article')!;
    expect(within(card).getByRole('link', { name: 'Acme' })).toHaveAttribute(
      'href',
      '/brand/acme/',
    );
    expect(within(card).getByText('Finance')).toBeInTheDocument();
    expect(within(card).getByRole('img', { name: 'Rating: 3.9 out of 5' })).toBeInTheDocument();
    expect(within(card).getByText('(12)')).toBeInTheDocument();
    expect(within(card).getByText('Acme excerpt.')).toBeInTheDocument();
    expect(within(card).getByText(/Quick and painless/)).toBeInTheDocument();
    expect(within(card).getByRole('link', { name: 'Acme was great' })).toHaveAttribute(
      'href',
      '/review/acme-best/',
    );
  });

  it('shows an excerpt as text, never as markup', async () => {
    respondWith(
      makePage([makeBrand('acme', { excerpt: 'Safe <b>bold</b> <img src=x onerror=1>' })]),
    );

    renderList();

    const card = (await screen.findByRole('heading', { name: 'Acme' })).closest('article')!;
    expect(within(card).getByText('Safe <b>bold</b> <img src=x onerror=1>')).toBeInTheDocument();
    expect(card.querySelector('b, img')).toBeNull();
  });

  it('copes with a brand that has no reviews', async () => {
    respondWith(
      makePage([makeBrand('quiet', { average_rating: null, review_count: 0, top_review: null })]),
    );

    renderList();

    expect(await screen.findByText('No ratings yet')).toBeInTheDocument();
    expect(screen.queryByRole('blockquote')).not.toBeInTheDocument();
  });

  it('keeps the previous results, dimmed and busy, while a new request is in flight', async () => {
    const user = userEvent.setup();
    const slow = deferred<Response>();
    respondWith(makePage([makeBrand('acme')]));
    fetchMock.mockReturnValueOnce(slow.promise);
    const { container } = renderList();
    await screen.findByRole('heading', { name: 'Acme' });

    await openIndustries(user);
    await user.click(checkbox('Telecom'));

    expect(screen.getByRole('heading', { name: 'Acme' })).toBeInTheDocument();
    expect(container.querySelector('.brand-list__results')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('status')).toHaveTextContent('Updating results');

    slow.resolve(jsonResponse(makePage([makeBrand('swift')])));

    expect(await screen.findByRole('heading', { name: 'Swift' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Acme' })).not.toBeInTheDocument();
    expect(container.querySelector('.brand-list__results')).toHaveAttribute('aria-busy', 'false');
  });
});

describe('URL as the source of truth', () => {
  it('reads the initial state from the URL', async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, '', '/brand/?industry=telecom&ordering=-review_count&page=2');
    respondWith(makePage([makeBrand('swift')], 20));

    renderList();

    await screen.findByRole('heading', { name: 'Swift' });
    expect(lastUrl()).toBe(
      '/api/brands/?industry=telecom&ordering=-review_count&page=2&page_size=12',
    );
    expect(industryButton()).toHaveAccessibleName('Industry 1 selected');
    expect(within(tagList()!).getByText('Telecom')).toBeInTheDocument();
    await openIndustries(user);
    expect(checkbox('Telecom')).toBeChecked();
    expect(checkbox('Finance')).not.toBeChecked();
    expect(sortButton()).toHaveTextContent('Most reviews');
  });

  it('writes a filter change to the URL, resets the page and refetches', async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, '', '/brand/?page=2');
    respondWith(makePage([makeBrand('acme')], 30), makePage([makeBrand('acme')]));
    renderList();
    await screen.findByRole('heading', { name: 'Acme' });

    await openIndustries(user);
    await user.click(checkbox('Finance'));

    expect(window.location.search).toBe('?industry=finance');
    await waitFor(() => expect(lastUrl()).toBe('/api/brands/?industry=finance&page_size=12'));
  });

  describe('sort options', () => {
    const option = (name: string) => screen.getByRole('option', { name });

    async function openSort() {
      const user = userEvent.setup();
      respondWith(makePage([makeBrand('acme')]), makePage([makeBrand('acme')]));
      renderList();
      await screen.findByRole('heading', { name: 'Acme' });
      return user;
    }

    it('opens a listbox with the current order selected', async () => {
      const user = await openSort();

      expect(sortButton()).toHaveAccessibleName('Sort by Name (A–Z)');
      await user.click(sortButton());

      const list = screen.getByRole('listbox', { name: 'Sort by' });
      expect(within(list).getAllByRole('option')).toHaveLength(5);
      expect(option('Name (A–Z)')).toHaveAttribute('aria-selected', 'true');
    });

    it('is walked with Tab and Shift+Tab, without choosing anything', async () => {
      const user = await openSort();
      sortButton().focus();

      await user.keyboard('{Enter}');
      expect(screen.getByRole('listbox')).toBeInTheDocument();
      await user.tab();
      expect(option('Name (A–Z)')).toHaveFocus();
      await user.tab();
      expect(option('Highest rated')).toHaveFocus();
      await user.tab();
      expect(option('Lowest rated')).toHaveFocus();
      await user.tab({ shift: true });
      expect(option('Highest rated')).toHaveFocus();

      expect(window.location.search).toBe('');
      expect(option('Name (A–Z)')).toHaveAttribute('aria-selected', 'true');
    });

    it('closes when you tab past the last option', async () => {
      const user = await openSort();
      await user.click(sortButton());
      await user.tab();

      await user.keyboard('{End}');
      expect(option('Fewest reviews')).toHaveFocus();
      await user.tab();

      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
      expect(window.location.search).toBe('');
    });

    it('moves through the options with the arrows too, without choosing', async () => {
      const user = await openSort();
      await user.click(sortButton());
      await user.tab();

      await user.keyboard('{ArrowDown}{ArrowDown}');

      expect(option('Lowest rated')).toHaveFocus();
      expect(window.location.search).toBe('');
      expect(screen.getByRole('listbox')).toBeInTheDocument();

      await user.keyboard('{ArrowUp}');
      expect(option('Highest rated')).toHaveFocus();
    });

    it('stops at the first and last option, and Home and End jump there', async () => {
      const user = await openSort();
      await user.click(sortButton());
      await user.tab();

      await user.keyboard('{ArrowUp}');
      expect(option('Name (A–Z)')).toHaveFocus();
      await user.keyboard('{End}');
      expect(option('Fewest reviews')).toHaveFocus();
      await user.keyboard('{ArrowDown}');
      expect(option('Fewest reviews')).toHaveFocus();
      await user.keyboard('{Home}');
      expect(option('Name (A–Z)')).toHaveFocus();
    });

    it('chooses with Enter, applies it and returns focus to the button', async () => {
      const user = await openSort();
      await user.click(sortButton());
      await user.tab();

      await user.keyboard('{Tab}{Enter}');

      expect(window.location.search).toBe('?ordering=-average_rating');
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
      expect(sortButton()).toHaveFocus();
      await waitFor(() =>
        expect(lastUrl()).toBe('/api/brands/?ordering=-average_rating&page_size=12'),
      );
    });

    it('chooses with Space too', async () => {
      const user = await openSort();
      await user.click(sortButton());

      await user.tab();
      await user.keyboard('{End} ');

      expect(window.location.search).toBe('?ordering=review_count');
    });

    it('jumps to an option by its first letter, cycling on repeats', async () => {
      const user = await openSort();
      await user.click(sortButton());
      await user.tab();

      await user.keyboard('l');
      expect(option('Lowest rated')).toHaveFocus();
      await user.keyboard('m');
      expect(option('Most reviews')).toHaveFocus();
      await user.keyboard('n');
      expect(option('Name (A–Z)')).toHaveFocus();
      expect(window.location.search).toBe('');
    });

    it('closes on Escape without choosing and returns focus to the button', async () => {
      const user = await openSort();
      await user.click(sortButton());
      await user.tab();
      await user.keyboard('{Tab}{Escape}');

      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
      expect(sortButton()).toHaveFocus();
      expect(window.location.search).toBe('');
    });

    it('can be chosen with the mouse', async () => {
      const user = await openSort();

      await user.click(sortButton());
      await user.click(option('Highest rated'));

      expect(window.location.search).toBe('?ordering=-average_rating');
      expect(sortButton()).toHaveFocus();
    });
  });

  it('follows browser back and forward', async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse(makePage([makeBrand('acme')]))),
    );
    renderList();
    await screen.findByRole('heading', { name: 'Acme' });
    await openIndustries(user);
    await user.click(checkbox('Telecom'));
    expect(checkbox('Telecom')).toBeChecked();

    window.history.back();

    await waitFor(() => expect(checkbox('Telecom')).not.toBeChecked());
    expect(window.location.search).toBe('');
    expect(tagList()).not.toBeInTheDocument();
  });

  it('falls back to page 1 without adding a history entry when the page is out of range', async () => {
    window.history.replaceState(null, '', '/brand/?page=9');
    const entries = window.history.length;
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'Invalid page.' }, 404));
    respondWith(makePage([makeBrand('acme')]));

    renderList();

    expect(await screen.findByRole('heading', { name: 'Acme' })).toBeInTheDocument();
    expect(window.location.search).toBe('');
    expect(window.history.length).toBe(entries);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('empty and error states', () => {
  it('explains an empty result and offers to clear the filters', async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, '', '/brand/?industry=telecom');
    respondWith(makePage([]), makePage([makeBrand('acme')]));
    renderList();

    expect(await screen.findByText('No brands match these filters.')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('No brands found.');
    expect(screen.getAllByRole('button', { name: 'Clear filters' })).toHaveLength(1);

    await user.click(screen.getByRole('button', { name: 'Clear filters' }));

    expect(await screen.findByRole('heading', { name: 'Acme' })).toBeInTheDocument();
    expect(window.location.search).toBe('');
    expect(industryButton()).toHaveFocus(); // the button that was clicked is gone
  });

  it('shows an alert with a retry that recovers', async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({}, 500)));
    renderList();

    expect(await screen.findByRole('alert')).toHaveTextContent('couldn’t load the brands');
    expect(fetchMock).toHaveBeenCalledTimes(3); // the first try plus two retries

    fetchMock.mockReset();
    respondWith(makePage([makeBrand('acme')]));
    await user.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await screen.findByRole('heading', { name: 'Acme' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('does not retry a client error', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({}, 400)));
    renderList();

    await screen.findByRole('alert');

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('shows a network failure the same way', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    renderList();

    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });

  it('does not show results from a different filter under an error', async () => {
    const user = userEvent.setup();
    respondWith(makePage([makeBrand('acme')]));
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({}, 500)));
    renderList();
    await screen.findByRole('heading', { name: 'Acme' });

    await openIndustries(user);
    await user.click(checkbox('Telecom'));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Acme' })).not.toBeInTheDocument();
  });
});

describe('pagination', () => {
  it('is hidden when everything fits on one page', async () => {
    respondWith(makePage([makeBrand('acme')]));
    renderList();
    await screen.findByRole('heading', { name: 'Acme' });

    expect(screen.queryByRole('navigation', { name: 'Pagination' })).not.toBeInTheDocument();
  });

  it('pages with real links, updates the URL and moves focus to the results', async () => {
    const user = userEvent.setup();
    respondWith(makePage([makeBrand('acme')], 30), makePage([makeBrand('urban')], 30));
    renderList();
    await screen.findByRole('heading', { name: 'Acme' });
    const nav = screen.getByRole('navigation', { name: 'Pagination' });
    expect(within(nav).getByRole('link', { name: '1' })).toHaveAttribute('aria-current', 'page');
    const next = within(nav).getByRole('link', { name: 'Next' });
    expect(next).toHaveAttribute('href', '/brand/?page=2');

    await user.click(next);

    expect(window.location.search).toBe('?page=2');
    expect(screen.getByRole('heading', { name: 'Brand results' })).toHaveFocus();
    expect(await screen.findByRole('heading', { name: 'Urban' })).toBeInTheDocument();
    expect(lastUrl()).toBe('/api/brands/?page=2&page_size=12');
    expect(screen.getByRole('status')).toHaveTextContent('Showing 13–13 of 30 brands');
  });

  it('shows Previous as unavailable on the first page', async () => {
    respondWith(makePage([makeBrand('acme')], 30));
    renderList();
    await screen.findByRole('heading', { name: 'Acme' });

    expect(screen.queryByRole('link', { name: 'Previous' })).not.toBeInTheDocument();
    expect(screen.getByText('Previous')).toHaveAttribute('aria-disabled', 'true');
  });
});

describe('industry dropdown', () => {
  beforeEach(() => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse(makePage([makeBrand('acme')]))),
    );
  });

  it('opens and closes from the button, announcing its state', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByRole('heading', { name: 'Acme' });
    expect(industryButton()).toHaveAttribute('aria-expanded', 'false');
    expect(industryButton()).not.toHaveAttribute('aria-controls');

    const menu = await openIndustries(user);

    expect(industryButton()).toHaveAttribute('aria-expanded', 'true');
    expect(industryButton()).toHaveAttribute('aria-controls', menu.id);

    await user.click(industryButton());

    expect(screen.queryByRole('group', { name: 'Industry' })).not.toBeInTheDocument();
    expect(industryButton()).toHaveAttribute('aria-expanded', 'false');
  });

  it('lists every industry with its brand count, described for assistive technology', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByRole('heading', { name: 'Acme' });

    const menu = await openIndustries(user);

    expect(within(menu).getAllByRole('checkbox')).toHaveLength(2);
    expect(checkbox('Finance')).toHaveAccessibleDescription('4 brands');
    expect(checkbox('Telecom')).toHaveAccessibleDescription('1 brand');
    expect(within(menu).getByText('4')).toBeInTheDocument(); // the visible count
  });

  it('copes with industries that have no counts', async () => {
    const user = userEvent.setup();
    renderList([{ name: 'Retail', slug: 'retail' }]);
    await screen.findByRole('heading', { name: 'Acme' });

    await openIndustries(user);

    expect(checkbox('Retail')).not.toHaveAccessibleDescription();
  });

  it('stays open while choosing, and shows each choice as a tag and a count on the button', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByRole('heading', { name: 'Acme' });
    await openIndustries(user);

    await user.click(checkbox('Finance'));
    await user.click(checkbox('Telecom'));

    expect(screen.getByRole('group', { name: 'Industry' })).toBeInTheDocument();
    expect(industryButton()).toHaveAccessibleName('Industry 2 selected');
    expect(window.location.search).toBe('?industry=finance&industry=telecom');
    const tags = within(tagList()!);
    expect(tags.getByText('Finance')).toBeInTheDocument();
    expect(tags.getByText('Telecom')).toBeInTheDocument();
  });

  it('removes a filter from its tag and moves focus to the next tag', async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, '', '/brand/?industry=finance&industry=telecom');
    renderList();
    await screen.findByRole('heading', { name: 'Acme' });

    await user.click(screen.getByRole('button', { name: 'Remove Finance filter' }));

    expect(window.location.search).toBe('?industry=telecom');
    expect(screen.queryByRole('button', { name: 'Remove Finance filter' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove Telecom filter' })).toHaveFocus();
  });

  it('returns focus to the Industry button when the last tag is removed', async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, '', '/brand/?industry=finance');
    renderList();
    await screen.findByRole('heading', { name: 'Acme' });

    await user.click(screen.getByRole('button', { name: 'Remove Finance filter' }));

    expect(tagList()).not.toBeInTheDocument();
    expect(industryButton()).toHaveFocus();
  });

  it('clears everything from "Clear all" and returns focus to the button', async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, '', '/brand/?industry=finance&industry=telecom');
    renderList();
    await screen.findByRole('heading', { name: 'Acme' });

    await user.click(screen.getByRole('button', { name: 'Clear all' }));

    expect(window.location.search).toBe('');
    expect(tagList()).not.toBeInTheDocument();
    expect(industryButton()).toHaveFocus();
  });

  it('offers Clear inside the panel only when something is chosen, and keeps the panel open', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByRole('heading', { name: 'Acme' });
    const menu = await openIndustries(user);
    expect(within(menu).queryByRole('button', { name: 'Clear' })).not.toBeInTheDocument();

    await user.click(checkbox('Finance'));
    await user.click(within(menu).getByRole('button', { name: 'Clear' }));

    expect(window.location.search).toBe('');
    expect(screen.getByRole('group', { name: 'Industry' })).toBeInTheDocument();
    expect(checkbox('Finance')).not.toBeChecked();
  });

  it('closes from Done and from Escape, returning focus to the button', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByRole('heading', { name: 'Acme' });

    await openIndustries(user);
    await user.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.queryByRole('group', { name: 'Industry' })).not.toBeInTheDocument();
    expect(industryButton()).toHaveFocus();

    await openIndustries(user);
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('group', { name: 'Industry' })).not.toBeInTheDocument();
    expect(industryButton()).toHaveFocus();
  });

  it('closes when you click elsewhere or tab out of it, but not when you click inside', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByRole('heading', { name: 'Acme' });

    await openIndustries(user);
    await user.click(checkbox('Finance'));
    expect(screen.getByRole('group', { name: 'Industry' })).toBeInTheDocument();

    await user.click(document.body);
    expect(screen.queryByRole('group', { name: 'Industry' })).not.toBeInTheDocument();

    await openIndustries(user);
    await user.click(sortButton()); // focus leaves
    expect(screen.queryByRole('group', { name: 'Industry' })).not.toBeInTheDocument();
  });

  it('still shows a removable tag for a slug that is not in the list', async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, '', '/brand/?industry=gone');
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(makePage([]))));
    renderList();

    await user.click(await screen.findByRole('button', { name: 'Remove gone filter' }));

    expect(window.location.search).toBe('');
  });

  it('renders a long list of industries in one scrollable panel', async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 40 }, (_, i) => ({
      name: `Industry ${i + 1}`,
      slug: `industry-${i + 1}`,
      brand_count: i,
    }));
    renderList(many);
    await screen.findByRole('heading', { name: 'Acme' });

    const menu = await openIndustries(user);

    expect(within(menu).getAllByRole('checkbox')).toHaveLength(40);
    expect(menu.querySelectorAll('.dropdown__options')).toHaveLength(1);
  });
});

describe('keyboard and accessibility', () => {
  it('can be driven entirely from the keyboard', async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse(makePage([makeBrand('acme')]))),
    );
    renderList();
    await screen.findByRole('heading', { name: 'Acme' });

    await user.tab();
    expect(industryButton()).toHaveFocus();
    await user.keyboard('{Enter}');
    await user.tab();
    expect(checkbox('Finance')).toHaveFocus();
    await user.keyboard(' ');
    expect(window.location.search).toBe('?industry=finance');

    await user.tab(); // Telecom
    await user.tab(); // Clear, which has appeared
    await user.tab(); // Done
    expect(screen.getByRole('button', { name: 'Done' })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(industryButton()).toHaveFocus();

    await user.tab();
    expect(sortButton()).toHaveFocus();
    await user.tab();
    expect(screen.getByRole('button', { name: 'Remove Finance filter' })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(window.location.search).toBe('');
    expect(industryButton()).toHaveFocus();
  });

  async function axeViolations(container: HTMLElement) {
    // Colour contrast needs real layout, which jsdom does not have.
    const results = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
    return results.violations;
  }

  it('has no axe violations with results showing', async () => {
    respondWith(makePage([makeBrand('acme'), makeBrand('urban')], 30));
    const { container } = renderList();
    await screen.findByRole('heading', { name: 'Acme' });

    expect(await axeViolations(container)).toEqual([]);
  });

  it('has no axe violations with the panel open and filters chosen', async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, '', '/brand/?industry=finance');
    respondWith(makePage([makeBrand('acme')]));
    const { container } = renderList();
    await screen.findByRole('heading', { name: 'Acme' });
    await openIndustries(user);

    expect(await axeViolations(container)).toEqual([]);
  });

  it('has no axe violations in the error and empty states', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({}, 500)));
    const { container } = renderList();
    await screen.findByRole('alert');

    expect(await axeViolations(container)).toEqual([]);
  });
});
