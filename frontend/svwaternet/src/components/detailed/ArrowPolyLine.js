import React from 'react';
import { DARKBLUECOLOR, LIGHTBLUECOLOR, PINKCOLOR } from './shared';

export function ArrowPolyLine({ points, sx = "0", sy = "0", stroke, prero, postro, concentrate, noarr, junctionPositions = [] }) {
    // this could've been done *much* more elegantly with regex
    const splitPoints = points.split(',').filter(word => word !== "");
    if (splitPoints.length < 3) {
        return (<></>)
    }
    const y1_x2_arr = splitPoints[1].split(' ').filter(word => word !== "");
    const y2_x3_arr = splitPoints[2].split(' ').filter(word => word !== "");

    const x1 = parseFloat(splitPoints[0].trim());
    const y1 = parseFloat(y1_x2_arr[0].trim());
    const x2 = parseFloat(y1_x2_arr[1].trim());
    const y2 = parseFloat(y2_x3_arr[0].trim());

    let angle = 90;
    if (x1 !== x2 || y1 !== y2) {
        angle = x1 <= x2
            ? (Math.atan((y2 - y1) / (x2 - x1)) * 180 / Math.PI) - 90
            : (Math.atan((y2 - y1) / (x2 - x1)) * 180 / Math.PI) + 90;
    }

    // default line color
    let lineStroke = stroke === undefined ? DARKBLUECOLOR : stroke;
    if (prero) {
        lineStroke = DARKBLUECOLOR;
    } else if (postro) {
        lineStroke = LIGHTBLUECOLOR;
    } else if (concentrate) {
        lineStroke = PINKCOLOR;
    }

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
}
