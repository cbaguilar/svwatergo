import React from 'react';
import { DARKBLUECOLOR, LIGHTBLUECOLOR, PINKCOLOR } from './shared';

const parsePoints = (points) => {
    if (!points || typeof points !== 'string') return [];
    return points
        .trim()
        .split(/\s+/)
        .map((pair) => pair.split(','))
        .filter((xy) => xy.length === 2)
        .map(([x, y]) => [Number.parseFloat(x), Number.parseFloat(y)])
        .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
};

export const ArrowPolyLine = React.memo(function ArrowPolyLine({
    points,
    sx = "0",
    sy = "0",
    stroke,
    prero,
    postro,
    concentrate,
    noarr,
    junctionPositions = [],
}) {
    const parsedPoints = parsePoints(points);
    if (parsedPoints.length < 2) return null;

    const [x1, y1] = parsedPoints[0];
    const nextPoint = parsedPoints.find(([x, y], idx) => idx > 0 && (x !== x1 || y !== y1));
    const [x2, y2] = nextPoint || [x1, y1];

    // base triangle points "up", rotate to align with first segment direction
    let angle = 0;
    if (x1 !== x2 || y1 !== y2) {
        angle = (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI + 90;
    }

    const lineStroke = prero
        ? DARKBLUECOLOR
        : postro
            ? LIGHTBLUECOLOR
            : concentrate
                ? PINKCOLOR
                : (stroke === undefined ? DARKBLUECOLOR : stroke);

    const junctions = junctionPositions.map((pos, index) => (
        <circle
            r="5"
            strokeWidth="0"
            cx={`${pos[0]}`}
            cy={`${pos[1]}`}
            fill={lineStroke}
            key={`(${index})${JSON.stringify(pos)}`}
        />
    ));

    return (
        <g transform={`translate(${sx},${sy})`}>
            {junctions}
            {!noarr && <g transform={`translate(${x1},${y1}) rotate(${angle})`}>
                <polygon
                    points="-3,3 0,-3 3,3"
                    fill={lineStroke}
                    stroke={lineStroke}
                    strokeWidth="2" />
            </g>}
            <polyline
                points={points}
                fill="none"
                stroke={lineStroke}
                strokeWidth="2" />
        </g>
    );
});
