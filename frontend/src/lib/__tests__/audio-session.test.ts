import { afterEach, describe, expect, it, vi } from 'vitest';
import { allowAudioCapture, getMicrophone } from '../audio-session';

type Nav = Navigator & { audioSession?: { type: string } };

describe('audio-session', () => {
  afterEach(() => {
    delete (navigator as Nav).audioSession;
    vi.restoreAllMocks();
  });

  it('turns a playback session (set by the wheel) into play-and-record', () => {
    (navigator as Nav).audioSession = { type: 'playback' };
    allowAudioCapture();
    expect((navigator as Nav).audioSession!.type).toBe('play-and-record');
  });

  it('does nothing where the API is absent', () => {
    expect(() => allowAudioCapture()).not.toThrow();
  });

  it('sets the session before it asks for the microphone', async () => {
    const session = { type: 'playback' };
    (navigator as Nav).audioSession = session;
    const seen: string[] = [];
    const stream = {} as MediaStream;
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn(async () => { seen.push(session.type); return stream; }) },
    });
    await expect(getMicrophone({ audio: true })).resolves.toBe(stream);
    expect(seen).toEqual(['play-and-record']);
  });
});
