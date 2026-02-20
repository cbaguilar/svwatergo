import React from 'react';
import { RelativeText } from './RelativeText';

export function PressureTank({ x = "0", y = "0", text = "", textDir = "right" }) {
    return (
        <g transform={`translate(${x},${y})`}>
            <rect x="-22.5" y="-40" width="45" height="80" rx="10" ry="10" fill="#fff" stroke="#000" strokeWidth="2" />
            <RelativeText
                text={text}
                textDir={textDir}
                positions={[[0, -50], [30, 0], [0, 50], [-30, 0]]}
                small
            />
        </g>
    );
}
