'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, type ComponentProps } from 'react';
import { INSTANT_LOADING } from '@/lib/feature-flags';

type LinkProps = ComponentProps<typeof Link>;

interface PrefetchLinkProps extends LinkProps {
  /** Additional prefetch warmup on hover (e.g. warm API cache) */
  onWarmup?: () => void;
}

/**
 * Navigation link that aggressively prefetches on hover/focus.
 * Next.js App Router prefetches <Link> by default for viewport links,
 * but this explicitly calls router.prefetch on pointer/focus events
 * for faster transitions.
 */
export default function PrefetchLink({ onWarmup, onMouseEnter, onFocus, ...props }: PrefetchLinkProps) {
  const router = useRouter();
  const href = typeof props.href === 'string' ? props.href : props.href.pathname ?? '';

  const handleHover = useCallback(
    (e: React.MouseEvent<HTMLAnchorElement>) => {
      if (INSTANT_LOADING) {
        router.prefetch(href);
        onWarmup?.();
      }
      if (onMouseEnter) {
        (onMouseEnter as (e: React.MouseEvent<HTMLAnchorElement>) => void)(e);
      }
    },
    [router, href, onWarmup, onMouseEnter],
  );

  const handleFocus = useCallback(
    (e: React.FocusEvent<HTMLAnchorElement>) => {
      if (INSTANT_LOADING) {
        router.prefetch(href);
      }
      if (onFocus) {
        (onFocus as (e: React.FocusEvent<HTMLAnchorElement>) => void)(e);
      }
    },
    [router, href, onFocus],
  );

  return (
    <Link
      {...props}
      prefetch={true}
      onMouseEnter={handleHover}
      onFocus={handleFocus}
    />
  );
}
