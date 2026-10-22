import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';

import { Select } from './Select';

type Size = 'small' | 'large';
const OPTIONS = [
  { value: 'small', label: 'Small' },
  { value: 'large', label: 'Large' },
] as const;

function Harness({ onChange = () => {} }: { onChange?: (value: Size) => void }) {
  const [value, setValue] = useState<Size>('small');
  return (
    <Select
      label="Size"
      icon={<svg aria-hidden="true" />}
      value={value}
      options={OPTIONS}
      onChange={(next) => {
        setValue(next);
        onChange(next);
      }}
    />
  );
}

describe('Select', () => {
  it('shows the current choice, named for screen readers with what is being chosen', () => {
    render(<Harness />);

    expect(screen.getByRole('button', { name: 'Size Small' })).toBeInTheDocument();
  });

  it('works with any option list: choosing reports the value, updates the button and closes', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    await user.click(screen.getByRole('button', { name: 'Size Small' }));
    await user.click(screen.getByRole('option', { name: 'Large' }));

    expect(onChange).toHaveBeenCalledWith('large');
    expect(screen.getByRole('button', { name: 'Size Large' })).toHaveFocus();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('marks the current option and walks the options with Tab', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'Size Small' }));
    expect(screen.getByRole('option', { name: 'Small' })).toHaveAttribute('aria-selected', 'true');
    await user.tab();
    await user.tab();

    expect(screen.getByRole('option', { name: 'Large' })).toHaveFocus();
  });
});
