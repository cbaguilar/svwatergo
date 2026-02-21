import React from 'react';
import { getFlowColor } from './shared';
import { RelativeText } from './RelativeText';

export function PumpSymbol({ 
    x = 0, 
    y = 0, 
    innerText = null, 
    flow = null, 
    textDir = "right", 
    outerText = "",
    on_click = null,
    pumpKey = "",
    md = null,
}) {
    // pump symbol made up of a circle on top of a triangle
    const transstr = 'translate(' + x + ',' + y + ')';
    const resolvedFlow = (() => {
        if (flow !== null && flow !== undefined) return flow;
        if (!pumpKey || !md || typeof md.get !== 'function') return null;
        return md.get(pumpKey, "current_value");
    })();
    const resolvedInnerText = (() => {
        if (innerText !== null && innerText !== undefined) return innerText;
        if (!pumpKey || !md || typeof md.get !== 'function') return "";
        return md.get(pumpKey, "abbreviated_name") || "";
    })();
    const resolvedOnClick = (() => {
        if (typeof on_click === 'function') return on_click;
        if (!pumpKey || !md || typeof md.get !== 'function') return () => {};
        const fn = md.get(pumpKey, "on_click");
        return typeof fn === 'function' ? fn : () => {};
    })();
    const flowColor = getFlowColor(resolvedFlow);
    const handleActivate = (event) => {
        resolvedOnClick(event);
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
            style={{ cursor: 'pointer' }}
        >
            <polygon points="-20,20 0,-19 20,20" fill={flowColor} stroke="#000" strokeWidth="2" />
            {/* the pump has a small 2 character label in the middle of the circle */}
            <circle cx="0" cy="0" r="20" fill={flowColor} stroke="#000" strokeWidth="2" />
            <text x="0" y="2" textAnchor="middle" alignmentBaseline="middle" fontSize="20" fill="#000">{resolvedInnerText}</text>
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
