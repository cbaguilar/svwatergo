import React from 'react';
import { GREENCOLOR, REDCOLOR, WHITECOLOR, getFlowColor, isHandlerSelected } from './shared';
import { RelativeText } from './RelativeText';
import { StaticRelativeText } from './StaticRelativeText';
import { getAngle } from './getAngle';

export function ThreeWayValveIndicator({
    x = 0,
    y = 0,
    dir = "right",
    innerText = "",
    textDir = "right",
    outerText = "",
    east = null,
    north = null,
    west = null,
    on_click = () => {}
}) {
    // similar to the valve indicator, but it has three triangles
    // one pointing up, one pointing down, and one pointing to the right=

    let centerColor;
    if (west === null || east === null || north === null) {
        centerColor = WHITECOLOR;
    } else if ([west, east, north].filter(x => x === true).length === 1) {
        // if only one end is on, which doesn't make sense
        centerColor = WHITECOLOR;
    } else if (west && east && north) {
        centerColor = GREENCOLOR;
    } else if ((west && east) || (west && north) || (east && north)) {
        centerColor = GREENCOLOR;
    } else {
        centerColor = REDCOLOR;
    }


    const transstr = 'translate(' + x + ',' + y + ')'
        + ` rotate(${getAngle(dir)})`;
    const isSelected = isHandlerSelected(on_click);
    const interactiveStyle = isSelected
        ? {
            cursor: 'pointer',
            outline: 'none',
            filter: 'drop-shadow(0 0 4px rgba(255,32,32,0.95)) drop-shadow(0 0 10px rgba(255,0,0,0.90))',
        }
        : { cursor: 'pointer', outline: 'none' };
    const handleActivate = (event) => {
        on_click(event);
    };
    return (
        <g
            transform={transstr}
            onClick={handleActivate}
            onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleActivate(e);
                }
            }}
            tabIndex={0}
            role="button"
            style={interactiveStyle}
        >
            <polygon points="-30,20 -30,-20 0,0" fill={getFlowColor(east)} stroke="#000" strokeWidth="2" />
            <polygon points="-20,-30 20,-30 0,0" fill={getFlowColor(north)} stroke="#000" strokeWidth="2" />
            <polygon points="30,-20 30,20 0,0" fill={getFlowColor(west)} stroke="#000" strokeWidth="2" />
            <circle cx="0" cy="0" r="20" fill={centerColor} stroke="#000" strokeWidth="2" />
            <StaticRelativeText
                dir={dir}
                text={innerText}
                y={1}
            />
            <RelativeText
                dir={dir}
                textDir={textDir}
                text={outerText}
                positions={[[0, -35], [40, 2], [0, 31], [-40, 2]]}
                small
            />
        </g>

    )
}
