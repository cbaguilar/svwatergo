import React from 'react';
import { YELLOWCOLOR } from './shared';
import { ArrowPolyLine } from './ArrowPolyLine';
import { RelativeText } from './RelativeText';

export function ChemicalFeed({ x = "0", y = "0", textDir = "right", text = "" }) {
    return (
        <g transform={`translate(20,0)`}>
            <g transform={`translate(${x},${y})`}>
                <path d="M0,0 v30 q0,10 -10,10 h-20 q-10,0 -10,-10 v-30 z"
                    fill={YELLOWCOLOR} stroke="black" strokeWidth="2" />
                <rect x="-40" y="-20" width="40" height="20" stroke="black" fill="white"
                    strokeWidth="2" />
                <g transform="translate(-20,-40) rotate(45)">
                    <circle cx="0" cy="0" r="18" stroke="black" fill="white"
                        strokeWidth="2" />
                    <line x1="-18" y1="0" x2="18" y2="0" stroke="black" strokeWidth="2" />
                    <line x1="0" y1="18" x2="0" y2="-18" stroke="black" strokeWidth="2" />
                </g>
                <ArrowPolyLine points="-20,-15 -20,40" stroke="black" />
                <RelativeText
                    dir="right"
                    textDir={textDir}
                    text={text}
                    positions={[[-20, -67], [8, -5], [-20, 55], [-48, -5]]}
                    small
                />
            </g>
        </g>
    )
}
