import React from 'react';
import { RelativeText } from './RelativeText';

export function MultiMediaFilter({ x = "0", y = "0", textDir = "right", outerText = "" }) {
    // Looks like a pump, but the circle is replaced with a tall rounded rectangle
    //the label is below the shape
    const transstr = 'translate(' + x + ',' + y + ')';
    return (
        <g transform={transstr}>
            <polygon points="-20,20 0,-20 20,20" fill="#fff" stroke="#000" strokeWidth="2" />
            <rect x="-20" y="-80" width="40" height="100" rx="20" ry="20" fill="#fff" stroke="#000" strokeWidth="2" />
            <RelativeText
                dir="right"
                textDir={textDir}
                text={outerText}
                positions={[[0, -90], [28, -25], [0, 37], [-28, -25]]}
                small
            />
        </g>
    )
}
