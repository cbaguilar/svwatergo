import React from 'react';
import { getFlowColor, isHandlerSelected } from './shared';
import { RelativeText } from './RelativeText';
import { StaticRelativeText } from './StaticRelativeText';
import { getAngle } from './getAngle';

export function ValveIndicator({ 
    x = 0, 
    y = 0, 
    flow = null, 
    innerText = "", 
    dir = "right", 
    outerText = "", 
    textDir = "right",
    on_click = () => {}
}) {
    // Svg valve that is made up of a bowtie shape with a circle in the middle of it
    // it is about the size of a sensor and it has a label in the middle of the circle
    // it is red when the valve is closed and green when it is open
    //it can be oriented horizontally or vertically
    // the text orientation should always be normal
    const flowColor = getFlowColor(flow);
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
    const transstr = 'translate(' + x + ',' + y + ') '
        + `rotate(${getAngle(dir)})`
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
            {/* the bowtie shape made up of two horizontal triangles pointing towards each other */}
            <polygon points="-30,20 -30,-20 30,20 30,-20" fill={flowColor} stroke="#000" strokeWidth="2" />
            <circle cx="0" cy="0" r="20" fill={flowColor} stroke="#000" strokeWidth="2" />
            <StaticRelativeText
                dir={dir}
                text={innerText}
                y={1}
            />
            <RelativeText
                dir={dir}
                textDir={textDir}
                text={outerText}
                positions={[[0, -28], [40, 2], [0, 32], [-40, 2]]}
                small
            />
        </g>
    )
}
