import {
  type KeyboardEvent,
  type PointerEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import {
  formatYen,
  type SalonCashPoint,
  salonCashTicks,
} from "../../utils/salonView";

interface SalonCashChartProps {
  points: SalonCashPoint[];
  initialCash: number;
  totalWeeks: number;
  language: string;
}

const HEIGHT = 220;
const PAD = { top: 18, right: 84, bottom: 28, left: 64 };
/** 枠の幅を測るまでの仮の幅 */
const FALLBACK_WIDTH = 640;
/** これより狭いと、横軸の目盛りを間引く */
const NARROW_WIDTH = 480;

/**
 * 週末の現金の推移(1 系列の折れ線)。成功の線(開業資金)と、マイナスになったときの
 * 0 の線を基準線として引く。値は帳簿の表でも読めるため、ホバーは補助にとどめる。
 */
export default function SalonCashChart({
  points,
  initialCash,
  totalWeeks,
  language,
}: SalonCashChartProps) {
  const { t } = useTranslation();
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  // 文字が拡大縮小されないよう、viewBox を枠の実際の幅に合わせて描く
  const frameRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(FALLBACK_WIDTH);
  useEffect(() => {
    const frame = frameRef.current;
    if (!frame || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) setWidth(entry.contentRect.width);
    });
    observer.observe(frame);
    return () => observer.disconnect();
  }, []);
  const ticks = salonCashTicks([...points, { week: 0, cash: initialCash }]);
  const minTick = ticks[0];
  const maxTick = ticks[ticks.length - 1];
  const plotWidth = Math.max(1, width - PAD.left - PAD.right);
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;
  const x = (week: number) => PAD.left + (week / totalWeeks) * plotWidth;
  const y = (cash: number) =>
    PAD.top + ((maxTick - cash) / (maxTick - minTick || 1)) * plotHeight;
  const weekLabel = (week: number) =>
    week === 0
      ? t("salon.office.chartStart")
      : t("salon.office.chartWeek", { week });
  const path = points
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"}${x(point.week)},${y(point.cash)}`,
    )
    .join(" ");
  const last = points[points.length - 1];
  const active = activeIndex === null ? null : points[activeIndex];
  const xTickWeeks = (
    width < NARROW_WIDTH ? [0, 6, 12] : [0, 3, 6, 9, 12]
  ).filter((week) => week <= totalWeeks);

  const handlePointerMove = (event: PointerEvent<SVGRectElement>) => {
    const svg = event.currentTarget.ownerSVGElement;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * width;
    const week = ((svgX - PAD.left) / plotWidth) * totalWeeks;
    let nearest = 0;
    points.forEach((point, index) => {
      if (Math.abs(point.week - week) < Math.abs(points[nearest].week - week)) {
        nearest = index;
      }
    });
    setActiveIndex(nearest);
  };

  const handleKeyDown = (event: KeyboardEvent<SVGSVGElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const step = event.key === "ArrowLeft" ? -1 : 1;
    setActiveIndex((current) =>
      Math.min(
        points.length - 1,
        Math.max(0, (current ?? points.length - 1) + step),
      ),
    );
  };

  return (
    <figure className="salon-chart">
      <figcaption className="salon-chart__title">
        {t("salon.office.chartTitle")}
      </figcaption>
      <div className="salon-chart__frame" ref={frameRef}>
        <svg
          viewBox={`0 0 ${width} ${HEIGHT}`}
          role="img"
          aria-label={t("salon.office.chartDescription", {
            start: formatYen(initialCash, language),
            week: last.week,
            cash: formatYen(last.cash, language),
          })}
          // biome-ignore lint/a11y/noNoninteractiveTabindex: 矢印キーで週ごとの値を読むため
          tabIndex={0}
          onKeyDown={handleKeyDown}
          onFocus={() => setActiveIndex(points.length - 1)}
          onBlur={() => setActiveIndex(null)}
        >
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                className="salon-chart__grid"
                x1={PAD.left}
                x2={width - PAD.right}
                y1={y(tick)}
                y2={y(tick)}
              />
              <text
                className="salon-chart__axis"
                x={PAD.left - 8}
                y={y(tick)}
                textAnchor="end"
                dominantBaseline="middle"
              >
                {formatYen(tick, language)}
              </text>
            </g>
          ))}
          {minTick < 0 && (
            <line
              className="salon-chart__zero"
              x1={PAD.left}
              x2={width - PAD.right}
              y1={y(0)}
              y2={y(0)}
            />
          )}
          <line
            className="salon-chart__goal"
            x1={PAD.left}
            x2={width - PAD.right}
            y1={y(initialCash)}
            y2={y(initialCash)}
          />
          {xTickWeeks.map((week) => (
            <text
              key={week}
              className="salon-chart__axis"
              x={x(week)}
              y={HEIGHT - 8}
              textAnchor="middle"
            >
              {weekLabel(week)}
            </text>
          ))}
          {active && (
            <line
              className="salon-chart__crosshair"
              x1={x(active.week)}
              x2={x(active.week)}
              y1={PAD.top}
              y2={HEIGHT - PAD.bottom}
            />
          )}
          <path className="salon-chart__line" d={path} />
          <circle
            className="salon-chart__dot"
            cx={x(last.week)}
            cy={y(last.cash)}
            r={4}
          />
          {active && active !== last && (
            <circle
              className="salon-chart__dot"
              cx={x(active.week)}
              cy={y(active.cash)}
              r={4}
            />
          )}
          <text
            className="salon-chart__end-label"
            x={x(last.week) + 10}
            y={y(last.cash)}
            dominantBaseline="middle"
          >
            {formatYen(last.cash, language)}
          </text>
          <rect
            className="salon-chart__hit"
            x={PAD.left}
            y={PAD.top}
            width={plotWidth}
            height={plotHeight}
            onPointerMove={handlePointerMove}
            onPointerLeave={() => setActiveIndex(null)}
          />
        </svg>
        {active && (
          <div
            className="salon-chart__tooltip"
            style={{ left: `${(x(active.week) / width) * 100}%` }}
            aria-hidden
          >
            <strong>{formatYen(active.cash, language)}</strong>
            <span>{weekLabel(active.week)}</span>
          </div>
        )}
      </div>
      <p className="salon-chart__legend">
        <span className="salon-chart__goal-key" aria-hidden />
        {t("salon.office.chartGoal", {
          cash: formatYen(initialCash, language),
        })}
      </p>
    </figure>
  );
}
