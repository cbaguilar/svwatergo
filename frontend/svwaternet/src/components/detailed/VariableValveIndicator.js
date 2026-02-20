import React from 'react';
import { LIGHTGREYCOLOR, REDCOLOR } from './shared';
import { RelativeText } from './RelativeText';
import { StaticRelativeText } from './StaticRelativeText';
import { getAngle } from './getAngle';

export function VariableValveIndicator({
    x = 0,
    y = 0,
    percentOpen = 20,
    innerText = "",
    dir = "right",
    outerText = "",
    textDir = "right",
    on_click = () => {}
}) {
    // Svg valve that is made up of a bowtie shape with a circle in the middle of it
    // it is about the size of a sensor and it has a label in the middle of the circle
    // it is red when the valve is closed and green when it is open
    // it can be oriented horizontally or vertically
    // the text orientation should always be normal
    const transstr = 'translate(' + x + ',' + y + ') '
        + `rotate(${getAngle(dir)})`;
    const handleActivate = () => {
        on_click();
    };
    let PO = percentOpen / 100;
    PO = PO >= 1 ? 0.99999 : PO;

    return (
        <g>
            <g
                transform={transstr}
                onClick={handleActivate}
                onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        handleActivate();
                    }
                }}
                tabIndex={0}
                role="button"
                style={{ cursor: 'pointer' }}
            >
                {/* the bowtie shape made up of two horizontal triangles pointing towards each other */}
                <polygon points="-30,20 -30,-20 30,20 30,-20" fill={LIGHTGREYCOLOR} stroke="#000" strokeWidth="2" />
                <circle cx="0" cy="0" r="20" fill={REDCOLOR} stroke="#000" strokeWidth="2" />
                <circle cx="0" cy="0" r="14" fill={REDCOLOR} stroke="#000" strokeWidth="2" />
                <StaticRelativeText
                    dir={dir}
                    text={innerText}
                    y={1}
                />
                <RelativeText
                    dir={dir}
                    textDir={textDir}
                    text={outerText}
                    positions={[[0, -32], [40, 2], [0, 32], [-40, 2]]}
                    small
                />

            </g>
        </g>
    )
}
