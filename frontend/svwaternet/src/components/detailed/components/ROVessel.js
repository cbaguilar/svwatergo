import React from 'react';
import { LIGHTBLUECOLOR, titleProps } from './shared';
import { RelativeText } from './RelativeText';
import { getAngle } from './getAngle';

export function ROVessel({
    x = "0",
    y = "0",
    outerText = "",
    innerText = "",
    textDir = "right",
    dir = "right",
    nubPositions = []
}) {
    // example of nubPositions is [[40,50],[60,40],[40,50]]
    const nubs = nubPositions.map((nubPos, index) =>
        <rect
            width="10"
            height="10"
            stroke="black"
            strokeWidth="2"
            rx="3.5"
            x={`${nubPos[0] - 5}`}
            y={`${nubPos[1] - 5}`}
            fill="white"
            key={`${index}${JSON.stringify(nubPositions)}`}
        />)
    return (
        <g transform={`translate(${x},${y}) rotate(${getAngle(dir)})`}>
            <line
                x1="-70"
                y1="0"
                x2="70"
                y2="0"
                stroke={LIGHTBLUECOLOR}
                strokeWidth="10"
                strokeLinecap="round"
            />
            {nubs}
            <rect x="-65" y="-16" width="130" height="32" rx="10" ry="10" fill="#fff" stroke="#000" strokeWidth="2" />
            <text
                {...titleProps}
                textAnchor='middle'
                x="0"
                y="6"
            >{innerText}</text>
            <RelativeText
                dir={dir}
                text={outerText}
                textDir={textDir}
                positions={[[0, -27], [80, 2], [0, 30], [-80, 2]]}
                small
            />
        </g>
    );
}
