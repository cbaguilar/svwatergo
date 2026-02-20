import React from 'react';
import { RelativeText } from './RelativeText';

export function LiquidFillGaugeWrapper({
    x = "0",
    y = "0",
    fillLevel = 50,
    text = "",
    textDir = "right",
    fillColor = "#68b7fc"
}) {
    let percent_full = (parseFloat(`${fillLevel}`)/100);
    let percent_full_draw = Math.max(Math.min(percent_full, 1), 0);
    return (<>
        {/* <LiquidFillGauge // rerendering this was causing memory leaks :(
            scale={1.5}
            fillLevel={parseInt(fillLevel)}
            xPos={parseInt(x) / 1.5 - 20}
            yPos={parseInt(y) / 1.5 - 20} /> */}
        
        <g transform={`translate(${x},${y})`}>
            <rect 
                x={`${-29}`} y={`${-31}`}
                width="60" 
                height="75"
                fill="#fff" 
                stroke="#000" strokeWidth="2" />
            {percent_full_draw && <rect 
                x={`${-26}`} y={`${41 - percent_full_draw * 69}`}
                width="54" 
                height={`${percent_full_draw * 69}` } 
                fill={fillColor} 
                strokeWidth="0" />}
            <text
                x="0" y="5"
                textAnchor='middle'
                alignmentBaseline="middle"
                fontSize={"1.5rem"}
                strokeWidth="0"
                fill="#000">{`${(percent_full * 100).toFixed(2)}%`}
            </text>
            <RelativeText
                dir="right"
                textDir={textDir}
                text={text}
                positions={[[0, -39], [35, 2], [0, 60], [-35, 2]]}
                small />
        </g>

    </>)
}
