'use client';

interface RatingPoint {
  date: string;
  rating: number;
}

interface RatingChartProps {
  data: RatingPoint[];
  width?: number;
  height?: number;
  className?: string;
}

export default function RatingChart({ data, width = 600, height = 200, className = '' }: RatingChartProps) {
  if (data.length === 0) {
    return (
      <div className={`flex items-center justify-center text-sm text-gray-500 dark:text-gray-400 ${className}`} style={{ width, height }}>
        No rating history
      </div>
    );
  }

  const ratings = data.map(d => d.rating);
  const minRating = Math.min(...ratings) - 50;
  const maxRating = Math.max(...ratings) + 50;
  const ratingRange = maxRating - minRating || 1;

  const padding = { top: 20, right: 20, bottom: 30, left: 50 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  function x(i: number): number {
    return padding.left + (i / Math.max(data.length - 1, 1)) * chartWidth;
  }

  function y(rating: number): number {
    return padding.top + chartHeight - ((rating - minRating) / ratingRange) * chartHeight;
  }

  // Build SVG path
  const pathPoints = data.map((d, i) => `${x(i)},${y(d.rating)}`);
  const linePath = `M ${pathPoints.join(' L ')}`;

  // Area fill
  const areaPath = `${linePath} L ${x(data.length - 1)},${padding.top + chartHeight} L ${x(0)},${padding.top + chartHeight} Z`;

  // Y-axis ticks
  const yTicks: number[] = [];
  const tickStep = Math.ceil(ratingRange / 4 / 50) * 50;
  for (let v = Math.ceil(minRating / tickStep) * tickStep; v <= maxRating; v += tickStep) {
    yTicks.push(v);
  }

  // X-axis labels (show first, middle, last)
  const xLabels: { i: number; label: string }[] = [];
  if (data.length >= 1) xLabels.push({ i: 0, label: formatDate(data[0].date) });
  if (data.length >= 3) xLabels.push({ i: Math.floor(data.length / 2), label: formatDate(data[Math.floor(data.length / 2)].date) });
  if (data.length >= 2) xLabels.push({ i: data.length - 1, label: formatDate(data[data.length - 1].date) });

  function formatDate(dateStr: string): string {
    const d = new Date(dateStr);
    return `${d.getMonth() + 1}/${d.getFullYear().toString().slice(2)}`;
  }

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={className} style={{ maxWidth: width, width: '100%' }}>
      {/* Grid lines */}
      {yTicks.map(v => (
        <g key={v}>
          <line
            x1={padding.left}
            y1={y(v)}
            x2={width - padding.right}
            y2={y(v)}
            stroke="currentColor"
            strokeOpacity={0.1}
            strokeWidth={1}
          />
          <text
            x={padding.left - 8}
            y={y(v) + 4}
            textAnchor="end"
            className="fill-gray-400 dark:fill-gray-500"
            fontSize={10}
          >
            {v}
          </text>
        </g>
      ))}

      {/* Area */}
      <path d={areaPath} fill="var(--brand-primary)" fillOpacity={0.1} />

      {/* Line */}
      <path d={linePath} fill="none" stroke="var(--brand-primary)" strokeWidth={2} />

      {/* Data points */}
      {data.map((d, i) => (
        <circle
          key={i}
          cx={x(i)}
          cy={y(d.rating)}
          r={3}
          fill="var(--brand-primary)"
        />
      ))}

      {/* X-axis labels */}
      {xLabels.map(({ i, label }) => (
        <text
          key={i}
          x={x(i)}
          y={height - 5}
          textAnchor="middle"
          className="fill-gray-400 dark:fill-gray-500"
          fontSize={10}
        >
          {label}
        </text>
      ))}
    </svg>
  );
}
