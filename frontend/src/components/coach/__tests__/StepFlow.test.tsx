/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import StepFlow from '../StepFlow';
import { useStepFlow, type StepComplete } from '@/hooks/useStepFlow';

const coach = en.coach;

afterEach(cleanup);

/** StepFlow driven by the real hook, with a scripted answer checker. */
function Harness({
  total,
  answers,
  onStepComplete,
  onFollowUp,
}: {
  total: number;
  answers: boolean[];
  onStepComplete?: (r: StepComplete) => void;
  onFollowUp?: (m: string) => void;
}) {
  const flow = useStepFlow(total, onStepComplete);
  const n = React.useRef(0);
  return (
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      <button type="button" onClick={flow.move}>
        board-move
      </button>
      <StepFlow
        title="Game review"
        state={flow.state}
        prompt="Find the winning move"
        feedback={{ san: 'Nc7+', motif: 'fork', xp: 10, followUp: { label: 'Why not Nf6+?', message: 'Why not 13.Nf6+?' } }}
        onHint={vi.fn()}
        onUndo={flow.undo}
        onCheck={() => void flow.check(() => answers[n.current++] ?? false)}
        onRetry={flow.retry}
        onNext={flow.next}
        onFollowUp={onFollowUp}
      />
    </NextIntlClientProvider>
  );
}

const checkButton = () => screen.getByRole('button', { name: coach.stepCheck }) as HTMLButtonElement;

describe('StepFlow', () => {
  it('header with step count and progress; «Check» enabled only after a move', () => {
    render(<Harness total={3} answers={[true]} />);
    expect(screen.getByText('Game review')).toBeTruthy();
    expect(screen.getByText('Step 1 of 3')).toBeTruthy();
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('1');
    expect(screen.getByText(coach.stepMakeMove)).toBeTruthy();
    expect(checkButton().disabled).toBe(true);
    fireEvent.click(screen.getByText('board-move'));
    expect(checkButton().disabled).toBe(false);
    expect(screen.getByText(coach.stepMoved)).toBeTruthy();
  });

  it('correct: green panel with the move, motif, XP and follow-up chip; «Next» goes on', async () => {
    const onStepComplete = vi.fn();
    const onFollowUp = vi.fn();
    render(<Harness total={2} answers={[true]} onStepComplete={onStepComplete} onFollowUp={onFollowUp} />);
    fireEvent.click(screen.getByText('board-move'));
    await act(async () => fireEvent.click(checkButton()));
    expect(screen.getByTestId('step-flow').getAttribute('data-phase')).toBe('correct');
    expect(screen.getByText(`${coach.stepCorrect} Nc7+`)).toBeTruthy();
    expect(screen.getByText('fork')).toBeTruthy();
    expect(screen.getByTestId('step-xp').textContent).toBe('+10 XP');
    expect(onStepComplete).toHaveBeenCalledWith({ correct: true, attempts: 1, xp: 10 });
    fireEvent.click(screen.getByText('Why not Nf6+?'));
    expect(onFollowUp).toHaveBeenCalledWith('Why not 13.Nf6+?');
    fireEvent.click(screen.getByText(coach.stepNext));
    expect(screen.getByText('Step 2 of 2')).toBeTruthy();
    expect(screen.getByTestId('step-flow').getAttribute('data-phase')).toBe('idle');
  });

  it('wrong: red panel, «Try again» returns to the same step; the second try earns half XP', async () => {
    const onStepComplete = vi.fn();
    render(<Harness total={2} answers={[false, true]} onStepComplete={onStepComplete} />);
    fireEvent.click(screen.getByText('board-move'));
    await act(async () => fireEvent.click(checkButton()));
    expect(screen.getByText(`${coach.stepWrong} Nc7+`)).toBeTruthy();
    expect(screen.queryByTestId('step-xp')).toBeNull();
    expect(onStepComplete).toHaveBeenLastCalledWith({ correct: false, attempts: 1, xp: 0 });
    fireEvent.click(screen.getByText(coach.stepRetry));
    expect(screen.getByText('Step 1 of 2')).toBeTruthy();
    fireEvent.click(screen.getByText('board-move'));
    await act(async () => fireEvent.click(checkButton()));
    expect(onStepComplete).toHaveBeenLastCalledWith({ correct: true, attempts: 2, xp: 5 });
  });

  it('a move can be undone before checking', () => {
    render(<Harness total={1} answers={[]} />);
    fireEvent.click(screen.getByText('board-move'));
    fireEvent.click(screen.getByRole('button', { name: coach.stepUndo }));
    expect(checkButton().disabled).toBe(true);
  });

  it('a single step has no step count', () => {
    render(<Harness total={1} answers={[]} />);
    expect(screen.queryByText(/Step 1 of/)).toBeNull();
    expect(screen.queryByRole('progressbar')).toBeNull();
  });
});
