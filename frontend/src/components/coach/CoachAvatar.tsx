import React from 'react';
import Image from 'next/image';

/** The coach's face: the companion fox (static for now). */
export default function CoachAvatar({ size = 40 }: { size?: number }) {
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-(--coach-surface-2) ring-1 ring-(--coach-border)"
      style={{ width: size, height: size }}
    >
      <Image src="/gamification/companion-fox-idle.svg" alt="" width={size} height={size} unoptimized />
    </span>
  );
}
