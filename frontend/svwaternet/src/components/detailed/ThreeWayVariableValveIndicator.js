import React from 'react';
import { LIGHTGREYCOLOR, REDCOLOR, isHandlerSelected } from './shared';
import { RelativeText } from './RelativeText';
import { StaticRelativeText } from './StaticRelativeText';
import { getAngle } from './getAngle';

export function ThreeWayVariableValveIndicator({
    x = 0,
    y = 0,
    percentOpen1 = 20,
    percentOpen2 = 60,
    innerText = "",
    dir = "right",
    outerText = "",
    /* if true, valves will be set to inflow, outflow, inflow */
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
    const isSelected = isHandlerSelected(on_click);
    const interactiveStyle = isSelected
        ? {
            cursor: 'pointer',
            filter: 'drop-shadow(0 0 4px rgba(255,32,32,0.95)) drop-shadow(0 0 10px rgba(255,0,0,0.90))',
        }
        : { cursor: 'pointer' };
    const handleActivate = (event) => {
        on_click(event);
    };

    let PO1 = percentOpen1 / 100;
    PO1 = PO1 >= 1 ? 0.9999 : PO1;
    let PO2 = percentOpen2 / 100;
    PO2 = PO2 >= 1 ? 0.9999 : PO2;

    return (
        <g transform={'translate(' + x + ',' + y + ') '}>
            <g
                transform={`rotate(${getAngle(dir)})`}
                onClick={handleActivate}
                onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        handleActivate();
                    }
                }}
                tabIndex={0}
                role="button"
                style={interactiveStyle}
            >
                <polygon
                    points="-30,20 -30,-20 0,0"
                    fill={LIGHTGREYCOLOR}
                    stroke="#000"
                    strokeWidth="2" />
                <polygon
                    points="0,0 30,20 30,-20"
                    fill={LIGHTGREYCOLOR}
                    stroke="#000"
                    strokeWidth="2" />
                <polygon
                    points="20,-30 -20,-30 0,0"
                    fill={LIGHTGREYCOLOR}
                    stroke="#000"
                    strokeWidth="2" />
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
                    positions={[[0, -43], [40, 2], [0, 32], [-40, 2]]}
                    small
                />
            </g>
        </g>
    )
}
