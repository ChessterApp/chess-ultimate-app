import React from 'react';
import Image from 'next/image';

/** The coach's face: the Chesster zebra with glasses (static for now). */
export default function CoachAvatar({ size = 40 }: { size?: number }) {
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-(--coach-surface-2) ring-1 ring-(--coach-border)"
      style={{ width: size, height: size }}
    >
      <Image src="/static/images/chesster-logo-v3.png" alt="" width={size} height={size} className="h-full w-full object-cover" />
    </span>
  );
}
