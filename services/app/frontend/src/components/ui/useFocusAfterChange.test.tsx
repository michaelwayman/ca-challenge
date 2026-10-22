import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';

import { useFocusAfterChange } from './useFocusAfterChange';

function Harness() {
  const [items, setItems] = useState(['a', 'b', 'c']);
  const focusAfterUpdate = useFocusAfterChange(items);
  return (
    <>
      <button type="button">elsewhere</button>
      <ul>
        {items.map((item, index) => (
          <li key={item}>
            <button
              type="button"
              onClick={() => {
                // After the click, the button is gone: move to the one that took its place.
                focusAfterUpdate(() => document.querySelectorAll<HTMLElement>('li button')[index]);
                setItems(items.filter((i) => i !== item));
              }}
            >
              remove {item}
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}

describe('useFocusAfterChange', () => {
  it('puts focus where the lookup says once the change has rendered', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'remove a' }));

    expect(screen.getByRole('button', { name: 'remove b' })).toHaveFocus();
  });

  it('does nothing when no lookup was registered', async () => {
    render(<Harness />);

    expect(document.body).toHaveFocus();
  });
});
