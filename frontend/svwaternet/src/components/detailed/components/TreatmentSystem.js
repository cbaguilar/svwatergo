import React from 'react';
import { RelativeText } from './RelativeText';

export function TreatmentSystem({ x = "0", y = "0", text = "", textDir = "right" }) {
    return (
        <g transform={`translate(${x},${y})`}>
            <rect
                x="-40" y="-20"
                width="80"
                height="40"
                rx="2"
                fill="#fff"
                stroke="#000" strokeWidth="2" />
            <line
                x1="-39" y1="19" x2="39" y2="-19" strokeLinecap='round'
                stroke="black" strokeWidth="2" />
            <RelativeText
                text={text}
                textDir={textDir}
                positions={[[0, -30], [45, 0], [0, 30], [-45, 0]]}
                small
            />
        </g>
    );
}
