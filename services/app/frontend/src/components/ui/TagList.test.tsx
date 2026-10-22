import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { TagList } from './TagList';

const TAGS = [
  { key: 'a', label: 'Alpha' },
  { key: 'b', label: 'Beta' },
];

describe('TagList', () => {
  it('lists the tags under the given name, each with a remove button', () => {
    render(<TagList tags={TAGS} label="Chosen" onRemove={() => {}} />);

    const list = screen.getByRole('list', { name: 'Chosen' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Remove Alpha' })).toBeInTheDocument();
  });

  it('reports which tag was removed, and names the buttons however the caller says', async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();
    render(
      <TagList
        tags={TAGS}
        label="Chosen"
        onRemove={onRemove}
        removeLabel={(tag) => `Drop ${tag.label}`}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Drop Beta' }));

    expect(onRemove).toHaveBeenCalledWith('b');
  });

  it('offers Clear all only when it can do something', async () => {
    const user = userEvent.setup();
    const onClear = vi.fn();
    const { rerender } = render(<TagList tags={TAGS} label="Chosen" onRemove={() => {}} />);
    expect(screen.queryByRole('button', { name: 'Clear all' })).not.toBeInTheDocument();

    rerender(<TagList tags={TAGS} label="Chosen" onRemove={() => {}} onClear={onClear} />);
    await user.click(screen.getByRole('button', { name: 'Clear all' }));

    expect(onClear).toHaveBeenCalledOnce();
  });
});
