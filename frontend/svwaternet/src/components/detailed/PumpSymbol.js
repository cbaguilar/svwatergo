import React from 'react';
import { getFlowColor } from './shared';
import { RelativeText } from './RelativeText';

export function PumpSymbol({ 
    x = 0, 
    y = 0, 
    innerText = "", 
    flow = null, 
    textDir = "right", 
    outerText = "",
    on_click = ()=>{}
}) {
    // pump symbol made up of a circle on top of a triangle
    const transstr = 'translate(' + x + ',' + y + ')';
    const flowColor = getFlowColor(flow);
    const handleActivate = () => {
        on_click();
    };
    return (
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
            <polygon points="-20,20 0,-19 20,20" fill={flowColor} stroke="#000" strokeWidth="2" />
            {/* the pump has a small 2 character label in the middle of the circle */}
            <circle cx="0" cy="0" r="20" fill={flowColor} stroke="#000" strokeWidth="2" />
            <text x="0" y="2" textAnchor="middle" alignmentBaseline="middle" fontSize="20" fill="#000">{innerText}</text>
            <RelativeText
                dir="right"
                textDir={textDir}
                text={outerText}
                positions={[[0, -28], [25, 2], [0, 32], [-25, 2]]}
                small
            />
        </g>
    )
}
