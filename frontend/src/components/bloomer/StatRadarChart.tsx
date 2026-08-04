const BLOOMER_AXIS_KEYS = [
  "allure",
  "technique",
  "depravity",
  "sensitivity",
  "endurance",
  "composure",
] as const;

type BloomerAxisKey = (typeof BLOOMER_AXIS_KEYS)[number];
type BloomerAxes = Record<BloomerAxisKey, number>;

interface RadarSeries {
  axes: BloomerAxes;
  color: string;
  label: string;
}

interface StatRadarChartProps {
  series: RadarSeries[];
  size?: number;
  maxValue?: number;
  axisLabels?: Partial<Record<BloomerAxisKey, string>>;
}

const AXIS_ANGLE_STEP = (Math.PI * 2) / BLOOMER_AXIS_KEYS.length;

function axisPoint(
  index: number,
  ratio: number,
  center: number,
  radius: number,
): [number, number] {
  const angle = index * AXIS_ANGLE_STEP - Math.PI / 2;
  const x = center + Math.cos(angle) * radius * ratio;
  const y = center + Math.sin(angle) * radius * ratio;
  return [x, y];
}

function pointsToPath(points: [number, number][]): string {
  return `${points.map((point) => point.join(",")).join(" ")}`;
}

export default function StatRadarChart({
  series,
  size = 220,
  maxValue = 100,
  axisLabels,
}: StatRadarChartProps) {
  const center = size / 2;
  const radius = size * 0.38;
  const gridLevels = [0.25, 0.5, 0.75, 1];

  return (
    <svg
      className="stat-radar-chart"
      viewBox={`0 0 ${size} ${size}`}
      width={size}
      height={size}
      role="img"
      aria-label="stat radar chart"
    >
      {gridLevels.map((level) => (
        <polygon
          key={level}
          className="stat-radar-chart__grid"
          points={pointsToPath(
            BLOOMER_AXIS_KEYS.map((_, index) =>
              axisPoint(index, level, center, radius),
            ),
          )}
        />
      ))}
      {BLOOMER_AXIS_KEYS.map((axis, index) => {
        const [x, y] = axisPoint(index, 1, center, radius);
        return (
          <line
            key={axis}
            className="stat-radar-chart__axis-line"
            x1={center}
            y1={center}
            x2={x}
            y2={y}
          />
        );
      })}
      {series.map((entry) => (
        <polygon
          key={entry.label}
          className="stat-radar-chart__series"
          style={{ stroke: entry.color, fill: entry.color }}
          points={pointsToPath(
            BLOOMER_AXIS_KEYS.map((axis, index) =>
              axisPoint(
                index,
                Math.min(1, Math.max(0, entry.axes[axis] / maxValue)),
                center,
                radius,
              ),
            ),
          )}
        />
      ))}
      {BLOOMER_AXIS_KEYS.map((axis, index) => {
        const [x, y] = axisPoint(index, 1.16, center, radius);
        return (
          <text
            key={axis}
            className="stat-radar-chart__label"
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="middle"
          >
            {axisLabels?.[axis] ?? axis}
          </text>
        );
      })}
    </svg>
  );
}
