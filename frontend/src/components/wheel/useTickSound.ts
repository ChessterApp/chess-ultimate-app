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

  const ensureCtx = useCallback((): AudioContext | null => {
    const Ctor = getAudioCtor();
    if (!Ctor) return null;
    if (!ctxRef.current) {
      try {
        ctxRef.current = new Ctor();
      } catch {
        return null;
      }
    }
    // Autoplay policies suspend the context until a user gesture; resume on use.
    if (ctxRef.current.state === 'suspended') {
      void ctxRef.current.resume();
    }
    return ctxRef.current;
  }, []);

  /** Play a short percussive click. */
  const tick = useCallback(() => {
    const ctx = ctxRef.current;
    if (!ctx || ctx.state !== 'running') return;
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
