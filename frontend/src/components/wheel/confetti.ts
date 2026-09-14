// Dependency-free confetti burst. Draws to a transient full-screen canvas and
// self-cleans when the animation finishes. No-op outside the browser.

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  rot: number;
  vrot: number;
  size: number;
  color: string;
}

const CONFETTI_COLORS = ['#c62828', '#f9a825', '#2e7d32', '#1565c0', '#6a1b9a', '#f5efe0'];

/** Fire a confetti burst from the top-center of the viewport. */
export function fireConfetti(count = 140): void {
  if (typeof document === 'undefined' || typeof window === 'undefined') return;

  const canvas = document.createElement('canvas');
  const dpr = window.devicePixelRatio || 1;
  const w = window.innerWidth;
  const h = window.innerHeight;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.cssText = `position:fixed;inset:0;width:${w}px;height:${h}px;pointer-events:none;z-index:9999;`;
  document.body.appendChild(canvas);

  const ctx = canvas.getContext('2d');
  if (!ctx) {
    canvas.remove();
    return;
  }
  ctx.scale(dpr, dpr);

  const particles: Particle[] = Array.from({ length: count }, () => ({
    x: w / 2 + (Math.random() - 0.5) * w * 0.5,
    y: -20,
    vx: (Math.random() - 0.5) * 8,
    vy: Math.random() * 4 + 2,
    rot: Math.random() * Math.PI,
    vrot: (Math.random() - 0.5) * 0.3,
    size: Math.random() * 8 + 4,
    color: CONFETTI_COLORS[Math.floor(Math.random() * CONFETTI_COLORS.length)],
  }));

  const gravity = 0.15;
  const start = performance.now();
  const duration = 2800;

  function frame(now: number) {
    const elapsed = now - start;
    ctx!.clearRect(0, 0, w, h);
    for (const p of particles) {
      p.vy += gravity;
      p.x += p.vx;
      p.y += p.vy;
      p.rot += p.vrot;
      ctx!.save();
      ctx!.translate(p.x, p.y);
      ctx!.rotate(p.rot);
      ctx!.globalAlpha = Math.max(0, 1 - elapsed / duration);
      ctx!.fillStyle = p.color;
      ctx!.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
      ctx!.restore();
    }
    if (elapsed < duration) {
      requestAnimationFrame(frame);
    } else {
      canvas.remove();
    }
  }
  requestAnimationFrame(frame);
}
