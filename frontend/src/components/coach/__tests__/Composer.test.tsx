/**
 * @vitest-environment jsdom
 */
import React, { useRef, useState } from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import en from '../../../../messages/en.json';
import Composer, { composerButton, type ComposerVoice } from '../Composer';

const coach = en.coach;

describe('composerButton', () => {
  const base = { hasText: false, streaming: false, voiceSupported: true, voiceActive: false };
  it('mic when empty, send with text, stop while streaming', () => {
    expect(composerButton(base)).toBe('mic');
    expect(composerButton({ ...base, hasText: true })).toBe('send');
    expect(composerButton({ ...base, hasText: true, streaming: true })).toBe('stop');
    expect(composerButton({ ...base, streaming: true })).toBe('stop');
  });
  it('keeps the mic while voice is on (to end it), even with text', () => {
    expect(composerButton({ ...base, hasText: true, voiceActive: true })).toBe('mic');
  });
  it('without voice support an empty field shows send', () => {
    expect(composerButton({ ...base, voiceSupported: false })).toBe('send');
  });
});

function Harness({ streaming = false, onAttach = vi.fn(), onSend = vi.fn(), onAbort = vi.fn(), voice = {} as Partial<ComposerVoice> }) {
  const [input, setInput] = useState('');
  const [attachOpen, setAttachOpen] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  return (
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      <Composer
        input={input}
        onInputChange={setInput}
        textareaRef={ref}
        placeholder={coach.inputPlaceholder}
        onKeyDown={() => {}}
        onPasteText={() => false}
        isStreaming={streaming}
        onSend={onSend}
        onAbort={onAbort}
        attachOpen={attachOpen}
        onAttachOpenChange={setAttachOpen}
        attachDisabled={false}
        onAttach={onAttach}
        voice={{
          supported: true,
          status: 'idle',
          active: false,
          error: null,
          quotaExhausted: false,
          remainingSeconds: null,
          onToggle: vi.fn(),
          onPrefetch: vi.fn(),
          ...voice,
        }}
      />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);

describe('Composer', () => {
  it('swaps the mic for send as soon as there is text', () => {
    const onSend = vi.fn();
    render(<Harness onSend={onSend} />);
    expect(screen.getByTestId('voice-toggle')).toBeTruthy();
    expect(screen.queryByTestId('composer-send')).toBeNull();
    fireEvent.change(screen.getByPlaceholderText(coach.inputPlaceholder), { target: { value: 'why a6?' } });
    expect(screen.queryByTestId('voice-toggle')).toBeNull();
    fireEvent.click(screen.getByTestId('composer-send'));
    expect(onSend).toHaveBeenCalledOnce();
  });

  it('shows stop while an answer streams', () => {
    const onAbort = vi.fn();
    render(<Harness streaming onAbort={onAbort} />);
    fireEvent.click(screen.getByTestId('composer-stop'));
    expect(onAbort).toHaveBeenCalledOnce();
  });

  it('the mic toggles voice', () => {
    const onToggle = vi.fn();
    render(<Harness voice={{ onToggle }} />);
    fireEvent.click(screen.getByTestId('voice-toggle'));
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it('`+` opens the attach sheet with every import, and a pick closes it', () => {
    const onAttach = vi.fn();
    render(<Harness onAttach={onAttach} />);
    fireEvent.click(screen.getByRole('button', { name: coach.attachMenu }));
    const items = screen.getAllByRole('menuitem').map((b) => b.textContent);
    expect(items).toEqual([coach.attachPaste, coach.attachUpload, coach.photoToPosition, coach.scoresheetToGame, coach.attachLink]);
    fireEvent.click(screen.getByRole('menuitem', { name: coach.attachLink }));
    expect(onAttach).toHaveBeenCalledWith('link');
    expect(screen.queryByTestId('attach-sheet')).toBeNull();
  });
});
