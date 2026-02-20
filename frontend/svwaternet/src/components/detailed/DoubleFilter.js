import React from 'react';
import { RelativeText } from './RelativeText';
import { SingleFilter } from './SingleFilter';

export function DoubleFilter({
    x = "0",
    y = "0",
    innerText1 = "",
    innerText2 = "",
    innerText3 = "",
    innerText4 = "",
    outerText = "",
    outerTextDir = "right"
}) {
    return (
        <g transform={`translate(-18,0)`}>
            <g transform={`translate(${x},${y})`}>
                <SingleFilter
                    x="0" y="0"
                    innerText1={innerText1}
                    innerText2={innerText2} />
                <SingleFilter
                    x="35" y="0"
                    innerText1={innerText3}
                    innerText2={innerText4} />
                <rect x="12" y="-24" width="8" height="8" fill="white" />
                <RelativeText
                    textDir={outerTextDir}
                    text={outerText}
                    positions={[[20, -37], [58, 0], [20, 43], [-20, 0]]}
                    small
                />
            </g>
        </g>
    );
}
