import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Notice } from './Notice';

describe('Notice', () => {
  it('is a plain message by default', () => {
    render(<Notice>Nothing here.</Notice>);

    expect(screen.getByText('Nothing here.')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('announces an error, and runs its action', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <Notice tone="error" action={{ label: 'Try again', onClick }}>
        It broke.
      </Notice>,
    );

    expect(screen.getByRole('alert')).toHaveTextContent('It broke.');
    await user.click(screen.getByRole('button', { name: 'Try again' }));

    expect(onClick).toHaveBeenCalledOnce();
  });
});
