type Item = number | 'gap';

/** Page numbers to show: first, last, and the current page with its neighbours. */
export function pageItems(current: number, total: number): Item[] {
  const wanted = new Set([1, total, current - 1, current, current + 1]);
  const pages = [...wanted].filter((page) => page >= 1 && page <= total).sort((a, b) => a - b);
  const items: Item[] = [];
  pages.forEach((page, index) => {
    const previous = pages[index - 1];
    if (previous !== undefined && page - previous > 1) items.push('gap');
    items.push(page);
  });
  return items;
}

interface PaginationProps {
  page: number;
  totalPages: number;
  /** The address of a page, so each link is real and "open in a new tab" works. */
  hrefFor: (page: number) => string;
  /** A plain left click is handled here instead of reloading the page. */
  onPage: (page: number) => void;
}

interface PageLinkProps {
  href: string;
  current?: boolean;
  onActivate: () => void;
  children: string;
}

function PageLink({ href, current = false, onActivate, children }: PageLinkProps) {
  return (
    <a
      className={`page-numbers${current ? ' current' : ''}`}
      href={href}
      aria-current={current ? 'page' : undefined}
      onClick={(event) => {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
        event.preventDefault();
        onActivate();
      }}
    >
      {children}
    </a>
  );
}

function DisabledLink({ children }: { children: string }) {
  return (
    <span className="page-numbers disabled" aria-disabled="true">
      {children}
    </span>
  );
}

export function Pagination({ page, totalPages, hrefFor, onPage }: PaginationProps) {
  if (totalPages <= 1) return null;

  const link = (target: number, label: string, current = false) => (
    <PageLink href={hrefFor(target)} current={current} onActivate={() => onPage(target)}>
      {label}
    </PageLink>
  );

  return (
    <nav aria-label="Pagination">
      <ul className="pagination">
        <li>{page > 1 ? link(page - 1, 'Previous') : <DisabledLink>Previous</DisabledLink>}</li>
        {pageItems(page, totalPages).map((item, index) => (
          <li key={item === 'gap' ? `gap-${index}` : item}>
            {item === 'gap' ? (
              <span className="dots" aria-hidden="true">
                &hellip;
              </span>
            ) : (
              link(item, String(item), item === page)
            )}
          </li>
        ))}
        <li>{page < totalPages ? link(page + 1, 'Next') : <DisabledLink>Next</DisabledLink>}</li>
      </ul>
    </nav>
  );
}
