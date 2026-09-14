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
const LABEL_R = 56; // mid-radius the labels are centered on (along each spoke)
const BULB_COUNT = 24;

interface WheelProps {
  segments: WheelSegment[];
  /** Current wheel rotation in degrees (clockwise). */
  rotation: number;
  spinning: boolean;
  /** Spin duration in ms — drives the CSS transition. */
  spinDurationMs: number;
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
function labelPlacement(angle: number): { x: number; y: number; transform: string } {
  const { x, y } = polarToCartesian(CENTER, CENTER, LABEL_R, angle);
  const flip = angle > 180;
  const theta = flip ? angle + 90 : angle - 90;
  return { x, y, transform: `rotate(${theta} ${x} ${y})` };
}

export default function Wheel({
  segments,
  rotation,
  spinning,
  spinDurationMs,
  spinLabel,
  disabled,
  onSpin,
  size,
}: WheelProps) {
  const count = segments.length;
  const seg = count > 0 ? segmentAngle(count) : 360;
  const fontSize = segmentFontSize(count);

  const stageStyle: React.CSSProperties = size
    ? { width: size, height: size }
    : { width: '100%', maxWidth: 560, aspectRatio: '1 / 1' };

  return (
    <div
      className={`wheel-stage relative${spinning ? ' is-spinning' : ''}`}
      style={stageStyle}
      data-testid="wheel-stage"
    >
      {/* Rotating disc: wedges + labels */}
      <div
        className={`wheel-disc absolute inset-0${spinning ? ' is-spinning' : ''}`}
        style={{
          transform: `rotate(${rotation}deg)`,
          transitionDuration: spinning ? `${spinDurationMs}ms` : '0ms',
          // Mirror the duration into a custom property so the reduced-motion
          // override in wheel.css can restore the full spin duration (the global
          // `* { transition-duration: 0.01ms !important }` kill switch would
          // otherwise flatten this inline value to an instant snap).
          ['--spin-ms' as string]: `${spinDurationMs}ms`,
        }}
        data-testid="wheel-disc"
      >
        <svg viewBox={`0 0 ${VIEW} ${VIEW}`} width="100%" height="100%" role="img" aria-label="prize wheel">
          {segments.map((s, i) => {
            const start = i * seg;
            const end = (i + 1) * seg;
            const center = segmentCenterAngle(i, count);
            const text = s.emoji ? `${s.emoji} ${s.label}` : s.label;
            const label = labelPlacement(center);
            return (
              <g key={s.id} data-testid="wheel-segment">
                <path
                  d={wedgePath(CENTER, CENTER, DISC_R, start, end)}
                  fill={s.color}
                  stroke="#3a1f10"
                  strokeWidth={0.6}
                />
                <text
                  x={label.x}
                  y={label.y}
                  transform={label.transform}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fontSize={fontSize}
                  fontWeight={700}
                  fill="#231007"
                  style={{ pointerEvents: 'none', userSelect: 'none' }}
                >
                  {text}
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
