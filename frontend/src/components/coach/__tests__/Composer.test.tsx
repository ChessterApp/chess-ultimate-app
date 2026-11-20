/**
 * @vitest-environment jsdom
 */
import React, { useRef, useState } from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import en from '../../../../messages/en.json';
import Composer, { bannerStage, composerButton, sendBesideMic, type ComposerVoice } from '../Composer';

const coach = en.coach;

describe('bannerStage (tester, 19.11: «не видно, включён он или нет»)', () => {
  it('the pipeline\'s step while voice is on, the status for Live, nothing when off', () => {
    expect(bannerStage({ stage: 'thinking', status: 'listening', active: true })).toBe('thinking');
    expect(bannerStage({ stage: 'hearing', status: 'listening', active: true })).toBe('hearing');
    expect(bannerStage({ status: 'speaking', active: true })).toBe('speaking');
    expect(bannerStage({ status: 'connecting', active: false })).toBe('connecting');
    expect(bannerStage({ stage: 'listening', status: 'listening', active: false })).toBeNull();
    expect(bannerStage({ status: 'error', active: true })).toBeNull();
  });
});

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
  it('text typed while voice is on gets a send button beside the mic (tester, 19.11)', () => {
    expect(sendBesideMic({ hasText: true, streaming: false, voiceActive: true })).toBe(true);
    expect(sendBesideMic({ hasText: false, streaming: false, voiceActive: true })).toBe(false);
    expect(sendBesideMic({ hasText: true, streaming: true, voiceActive: true })).toBe(false);
    expect(sendBesideMic({ hasText: true, streaming: false, voiceActive: false })).toBe(false);
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

  it('the banner: what was heard while the coach thinks, «Stop» ends the voice (tester, 19.11)', () => {
    const onToggle = vi.fn();
    render(<Harness voice={{ status: 'listening', active: true, stage: 'thinking', heard: 'how to answer Nf3', onToggle }} />);
    expect(screen.getByTestId('voice-banner').getAttribute('data-stage')).toBe('thinking');
    expect(screen.getByTestId('voice-banner-title').textContent).toBe(coach.voiceStage.thinking);
    expect(screen.getByText('Heard: “how to answer Nf3”')).toBeTruthy();
    fireEvent.click(screen.getByTestId('voice-banner-stop'));
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it('the banner: a level meter while the mic hears the student', () => {
    render(<Harness voice={{ status: 'listening', active: true, stage: 'hearing', level: 0.8 }} />);
    expect(screen.getByTestId('voice-banner-title').textContent).toBe(coach.voiceStage.hearing);
    const bars = screen.getByTestId('voice-level').querySelectorAll('span');
    expect(bars).toHaveLength(5);
    expect(parseInt((bars[2] as HTMLElement).style.height, 10)).toBeGreaterThan(15);
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
