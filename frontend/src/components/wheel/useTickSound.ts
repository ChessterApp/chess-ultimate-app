// Synthesized "tick" click via WebAudio — no audio files. Used when a segment
// boundary crosses the pointer during a spin. Gracefully no-ops if WebAudio is
// unavailable (SSR, older browsers).

import { useCallback, useEffect, useRef } from 'react';

type AudioCtor = typeof AudioContext;

function getAudioCtor(): AudioCtor | null {
  if (typeof window === 'undefined') return null;
  return (
    window.AudioContext ||
    (window as unknown as { webkitAudioContext?: AudioCtor }).webkitAudioContext ||
    null
  );
}

export function useTickSound() {
  const ctxRef = useRef<AudioContext | null>(null);

  /**
   * Create + unlock the AudioContext. Must be called from inside a real user
   * gesture (the spin tap). iOS/WebKit only unlocks output when a sound actually
   * starts during the gesture — resume() alone leaves the context suspended and
   * every later rAF-driven tick() would be dropped. Mirrors TugSound.unlock().
   *
   * Returns `true` only when the context is `running` afterwards; safe to call
   * on every spin (each tap is another chance to unlock).
   */
  const ensureCtx = useCallback((): boolean => {
    // Declare the iOS audio session so Web Audio ignores the silent switch.
    try {
      const nav = navigator as Navigator & { audioSession?: { type: string } };
      if (nav.audioSession) nav.audioSession.type = 'playback';
    } catch {
      /* not supported — ignore */
    }
    const Ctor = getAudioCtor();
    if (!Ctor) return false;
    if (!ctxRef.current) {
      try {
        ctxRef.current = new Ctor();
      } catch {
        return false;
      }
    }
    const ctx = ctxRef.current;
    // Autoplay policies suspend the context until a user gesture; resume on use.
    if (ctx.state === 'suspended') void ctx.resume().catch(() => {});
    // Play a 1-frame silent buffer inside the gesture to force-unlock WebKit.
    try {
      const buf = ctx.createBuffer(1, 1, 22050);
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);
      src.start(0);
    } catch {
      /* createBuffer/start can throw on a closed context — ignore */
    }
    return ctx.state === 'running';
  }, []);

  /** Play a short percussive click. */
  const tick = useCallback(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    if (ctx.state !== 'running') {
      // Still locked — nudge it rather than giving up for the whole spin. Skip
      // this click so ticks don't queue up and burst out once it resumes.
      if (ctx.state === 'suspended') void ctx.resume().catch(() => {});
      return;
    }
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'square';
    osc.frequency.setValueAtTime(1100, now);
    osc.frequency.exponentialRampToValueAtTime(600, now + 0.03);
    gain.gain.setValueAtTime(0.12, now);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.05);
    osc.connect(gain).connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.06);
  }, []);

  useEffect(() => {
    return () => {
      void ctxRef.current?.close();
      ctxRef.current = null;
    };
  }, []);

  return { ensureCtx, tick };
}
