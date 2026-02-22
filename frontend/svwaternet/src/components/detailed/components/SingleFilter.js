import React from 'react';
import { RelativeText } from './RelativeText';

export function SingleFilter({ x = 0, y = 0, outerText = "", textDir = "right", innerText1 = "", innerText2 = "", outerTextLarge, innerText1Large }) {
    const textProps = {
        alignmentBaseline: "middle",
        textAnchor: "middle",
        fontSize: innerText1Large ? "18" : "12",
        strokeWidth: "0",
        fill: "black"
    };

    return (
        <g transform="translate(17.2,-15)">
            <g transform={`translate(${x},${y})`} stroke="black" >
                <path d="M-4.5,0 v30 q0,13 -13,13 h-0 q-13,0 -13,-13 v-30 z" strokeWidth="2" fill="white" />
                <rect x="-35" y="-10" width="35" height="10" strokeWidth="2" fill="white" />
                <text x="-17" y="14" {...textProps}> {innerText1} </text>
                <text x="-17" y="27" {...textProps}> {innerText2} </text>
                <RelativeText
                    textDir={textDir}
                    positions={[[-17, -22], [5, 15], [-17, 55], [-38, 15]]}
                    text={outerText}
                    small={!outerTextLarge} />
            </g>
        </g>

    )
}
