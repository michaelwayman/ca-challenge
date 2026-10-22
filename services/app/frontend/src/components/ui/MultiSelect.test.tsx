import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';

import { MultiSelect } from './MultiSelect';

const OPTIONS = [
  { value: 'red', label: 'Red', count: 1 },
  { value: 'blue', label: 'Blue', count: 4 },
  { value: 'green', label: 'Green' },
];

function Harness({ initial = [] as string[] }) {
  const [selected, setSelected] = useState(initial);
  return (
    <MultiSelect
      label="Colour"
      icon={<svg aria-hidden="true" />}
      options={OPTIONS}
      selected={selected}
      onChange={setSelected}
      countNoun="shirts"
    />
  );
}

const button = () => screen.getByRole('button', { name: /^Colour/ });

describe('MultiSelect', () => {
  it('opens a group of checkboxes and applies each choice as it is made', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(button());
    const group = screen.getByRole('group', { name: 'Colour' });
    expect(group).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: /Blue/ }));
    await user.click(screen.getByRole('checkbox', { name: /Red/ }));

    expect(button()).toHaveAccessibleName('Colour 2 selected');
    expect(screen.getByRole('checkbox', { name: /Blue/ })).toBeChecked();
    expect(group).toBeInTheDocument(); // stays open while choosing
  });

  it('reads out each count with the noun it was given, and nothing when there is none', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(button());

    expect(screen.getByRole('checkbox', { name: /Red/ })).toHaveAccessibleDescription('1 shirt');
    expect(screen.getByRole('checkbox', { name: /Blue/ })).toHaveAccessibleDescription('4 shirts');
    expect(screen.getByRole('checkbox', { name: 'Green' })).toHaveAccessibleDescription('');
  });

  it('clears everything with Clear, and Done closes the menu', async () => {
    const user = userEvent.setup();
    render(<Harness initial={['red', 'blue']} />);

    await user.click(button());
    await user.click(screen.getByRole('button', { name: 'Clear' }));
    expect(button()).toHaveAccessibleName('Colour');
    expect(screen.queryByRole('button', { name: 'Clear' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.queryByRole('group')).not.toBeInTheDocument();
    expect(button()).toHaveFocus();
  });
});
