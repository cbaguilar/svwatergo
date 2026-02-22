import React from 'react';
import { ArrowPolyLine } from './ArrowPolyLine';
import { RelativeText } from './RelativeText';

export function Drain({ x = "0", y = "0", text = "", textDir = "right" }) {
    return (
        <g transform={`translate(${x},${y})`}>
            <ArrowPolyLine noarr stroke="black" points="-0.5, 18.5 -0.5, -1.5 -15.5, -16.5 -0.5, -1.5 14.5, -16.5" />
            <RelativeText
                dir="right"
                text={text}
                textDir={textDir}
                positions={[[0, -27], [20, 2], [0, 30], [-20, 2]]}
                small
            />
        </g>
    )
}
