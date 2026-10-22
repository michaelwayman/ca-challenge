import { fireEvent, render, screen } from '@testing-library/react';

import { Pagination } from './Pagination';

const hrefFor = (page: number) => `/things/?p=${page}`;

describe('Pagination', () => {
  it('renders nothing for a single page', () => {
    const { container } = render(
      <Pagination page={1} totalPages={1} hrefFor={hrefFor} onPage={() => {}} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('builds every link from hrefFor and marks the current page', () => {
    render(<Pagination page={2} totalPages={3} hrefFor={hrefFor} onPage={() => {}} />);

    expect(screen.getByRole('link', { name: '1' })).toHaveAttribute('href', '/things/?p=1');
    expect(screen.getByRole('link', { name: '2' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Next' })).toHaveAttribute('href', '/things/?p=3');
  });

  it('disables Previous on the first page and Next on the last', () => {
    const { rerender } = render(
      <Pagination page={1} totalPages={3} hrefFor={hrefFor} onPage={() => {}} />,
    );
    expect(screen.queryByRole('link', { name: 'Previous' })).not.toBeInTheDocument();
    expect(screen.getByText('Previous')).toHaveAttribute('aria-disabled', 'true');

    rerender(<Pagination page={3} totalPages={3} hrefFor={hrefFor} onPage={() => {}} />);
    expect(screen.queryByRole('link', { name: 'Next' })).not.toBeInTheDocument();
  });

  it('handles a plain click itself but leaves new-tab clicks to the browser', () => {
    const onPage = vi.fn();
    render(<Pagination page={1} totalPages={3} hrefFor={hrefFor} onPage={onPage} />);

    fireEvent.click(screen.getByRole('link', { name: '2' }), { ctrlKey: true });
    expect(onPage).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('link', { name: '2' }));
    expect(onPage).toHaveBeenCalledWith(2);
  });
});
