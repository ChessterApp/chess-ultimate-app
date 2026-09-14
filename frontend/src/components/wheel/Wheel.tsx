'use client';

import React from 'react';
import type { WheelSegment } from '@/lib/wheel/types';
import {
  segmentAngle,
  segmentCenterAngle,
  polarToCartesian,
  wedgePath,
  segmentFontSize,
} from '@/lib/wheel/geometry';
import './wheel.css';

const VIEW = 200;
const CENTER = VIEW / 2;
const DISC_R = 92; // wedge radius within the rotating disc
const RIM_R = 96; // gold rim radius (fixed frame)
const BULB_R = 96; // bulb ring radius (fixed frame)
const HUB_R = 16; // center hub radius
const LABEL_R = 60; // radius the text label sits on (pushed outward, near the emoji/rim)
const EMOJI_R = 74; // radius the enlarged emoji sits on (outer, along each spoke)
const BULB_COUNT = 24;

interface WheelProps {
  segments: WheelSegment[];
  /** Ref to the rotating disc; the physics driver writes `style.transform` here. */
  discRef?: React.Ref<HTMLDivElement>;
  /** Whether a spin is in progress — drives the decorative bulb chase only. */
  spinning: boolean;
  spinLabel: string;
  disabled: boolean;
  onSpin: () => void;
  /** Rendered pixel size of the square stage. Defaults to responsive 100%. */
  size?: number;
}

/** Radial label transform: the label sits on its wedge's spoke at LABEL_R and
 *  reads outward. Labels on the left half (bisector 180°–360°) are flipped 180°
 *  so text stays upright rather than upside-down. Returns the SVG transform and
 *  the anchor point it rotates around. */
function spokePlacement(angle: number, r: number): { x: number; y: number; transform: string } {
  const { x, y } = polarToCartesian(CENTER, CENTER, r, angle);
  const flip = angle > 180;
  const theta = flip ? angle + 90 : angle - 90;
  return { x, y, transform: `rotate(${theta} ${x} ${y})` };
}

export default function Wheel({
  segments,
  discRef,
  spinning,
  spinLabel,
  disabled,
  onSpin,
  size,
}: WheelProps) {
  const count = segments.length;
  const seg = count > 0 ? segmentAngle(count) : 360;
  const fontSize = segmentFontSize(count);
  // Emoji sized to fit inside its wedge (halved from the old icon-first size).
  const emojiFontSize = Math.round(fontSize * 0.95);
  // Label text halved so it fits neatly beside its emoji near the wedge edge.
  const labelFontSize = Math.round(fontSize * 0.5);

  const stageStyle: React.CSSProperties = size
    ? { width: size, height: size }
    : { width: '100%', maxWidth: 560, aspectRatio: '1 / 1' };

  return (
    <div
      className={`wheel-stage relative${spinning ? ' is-spinning' : ''}`}
      style={stageStyle}
      data-testid="wheel-stage"
    >
      {/* Rotating disc: wedges + labels. Rotation is written straight to
          `style.transform` by the physics driver via `discRef` — no CSS
          transition, no per-frame React render. */}
      <div
        ref={discRef}
        className={`wheel-disc absolute inset-0${spinning ? ' is-spinning' : ''}`}
        data-testid="wheel-disc"
      >
        <svg viewBox={`0 0 ${VIEW} ${VIEW}`} width="100%" height="100%" role="img" aria-label="prize wheel">
          {segments.map((s, i) => {
            const start = i * seg;
            const end = (i + 1) * seg;
            const center = segmentCenterAngle(i, count);
            const label = spokePlacement(center, s.emoji ? LABEL_R : (LABEL_R + EMOJI_R) / 2);
            const emoji = spokePlacement(center, EMOJI_R);
            return (
              <g key={s.id} data-testid="wheel-segment">
                <path
                  d={wedgePath(CENTER, CENTER, DISC_R, start, end)}
                  fill={s.color}
                  stroke="#3a1f10"
                  strokeWidth={0.6}
                />
                {s.emoji && (
                  <text
                    x={emoji.x}
                    y={emoji.y}
                    transform={emoji.transform}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fontSize={emojiFontSize}
                    style={{ pointerEvents: 'none', userSelect: 'none' }}
                  >
                    {s.emoji}
                  </text>
                )}
                <text
                  x={label.x}
                  y={label.y}
                  transform={label.transform}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fontSize={labelFontSize}
                  fontWeight={700}
                  fill="#231007"
                  style={{ pointerEvents: 'none', userSelect: 'none' }}
                >
                  {s.label}
                </text>
              </g>
            );
          })}
          {/* inner hub */}
          <circle cx={CENTER} cy={CENTER} r={HUB_R} fill="#3a1f10" stroke="#e9b949" strokeWidth={2} />
        </svg>
      </div>

      {/* Fixed frame: gold rim, chasing bulbs, pointer */}
      <svg
        viewBox={`0 0 ${VIEW} ${VIEW}`}
        width="100%"
        height="100%"
        className="absolute inset-0"
        style={{ pointerEvents: 'none' }}
        aria-hidden="true"
      >
        <circle cx={CENTER} cy={CENTER} r={RIM_R} fill="none" stroke="#a9782b" strokeWidth={8} />
        <circle cx={CENTER} cy={CENTER} r={RIM_R} fill="none" stroke="#e9b949" strokeWidth={3} />
        {Array.from({ length: BULB_COUNT }, (_, i) => {
          const a = (i / BULB_COUNT) * 360;
          const rad = (a * Math.PI) / 180;
          const bx = CENTER + BULB_R * Math.sin(rad);
          const by = CENTER - BULB_R * Math.cos(rad);
          return (
            <circle
              key={i}
              className="wheel-bulb"
              cx={bx}
              cy={by}
              r={2.6}
              style={{ ['--i' as string]: i }}
            />
          );
        })}
        {/* pointer at top, pointing down into the wheel */}
        <polygon points={`${CENTER - 8},2 ${CENTER + 8},2 ${CENTER},20`} fill="#e9b949" stroke="#a9782b" strokeWidth={1.5} />
      </svg>

      {/* Center spin button */}
      <button
        type="button"
        className="wheel-spin-btn"
        style={{ width: '22%', height: '22%', fontSize: 'clamp(11px, 3vw, 20px)' }}
        onClick={onSpin}
        disabled={disabled}
        aria-label={spinLabel}
      >
        {spinLabel}
      </button>
    </div>
  );
}
