import React from 'react';
import { RelativeText } from './RelativeText';
import { getAngle } from './getAngle';

export function CheckValve({ x = "0", y = "0", dir = "right", textDir = "right", text = "" }) {

    //Long capital N-shaped line with an arrow above it pointing
    //to the right.

    const textPositions = [[20, 0], [51, 21.5], [20, 40], [-11, 21.5]];
    const transstr = 'translate(' + x + ',' + y + ')';
    return (
        <g transform="translate(-19,-21)">
            <g transform={transstr}>
                <g transform={`rotate(${getAngle(dir)}, 18.75, 22.5)`}>
                    {/* <polyline points="0,65 0,25 75,65 75,25" strokeWidth="2" fill="none" stroke="#000" />        
                <polyline points="10,15 65,15" strokeWidth="2" fill="none" stroke="#000" />        
                <polygon  points="60,10 65,15 60,20" strokeWidth="2" fill="black" stroke="#000" /> */}
                    <polyline points="0,32.5 0,12.5 37.5,32.5 37.5,12.5" strokeWidth="2" fill="none" stroke="#000" />
                    <polyline points="5,7.5 32.5,7.5" strokeWidth="2" fill="none" stroke="#000" />
                    <polygon points="30,5 32.5,7.5 30,10" strokeWidth="2" fill="black" stroke="#000" />

                    <RelativeText
                        dir={dir}
                        textDir={textDir}
                        text={text}
                        positions={textPositions}
                    />
                </g>
            </g>
        </g>
    )
}
