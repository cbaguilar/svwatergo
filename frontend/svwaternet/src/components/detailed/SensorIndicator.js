import React from 'react';
import spinnerUrl from "./spinner.svg";
import { BLUECOLOR, LIGHTGREYCOLOR } from './shared';
import { RelativeText } from './RelativeText';

export function SensorIndicator({
    x = "0",
    y = "0",
    innerText = "",
    outerText = "",
    line = null,
    textDir = "right",
    smallInner = false,
    WaterScope = false,
    loadIfBlank = true,
    on_click = ()=>{}
}) {
    // svg sensor indicator, circle about the size of a pump with a small label in the middle
    // it has a red border if the sensor is not working
    // it also has a small numerical indicator either above, below, or to either side
    // of the circle with the value of the sensor and its unit
    const transstr = 'translate(' + x + ',' + y + ')';

    const color = WaterScope ? LIGHTGREYCOLOR : BLUECOLOR;
    const handleActivate = () => {
        on_click();
    };

    const LINELENGTH = 35;
    let sensorLine;




    switch (line) {
        case ("down"):
            sensorLine = <line x1="0" y1={`${LINELENGTH}`} x2="0" y2="0"
                stroke="black" strokeWidth="2" />
            break;
        case ("up"):
            sensorLine = <line x1="0" y1={`-${LINELENGTH}`} x2="0" y2="0"
                stroke="black" strokeWidth="2" />
            break;
        case ("left"):
            sensorLine = <line x1={`-${LINELENGTH}`} y1="0" x2="0" y2="0"
                stroke="black" strokeWidth="2" />
            break;
        case ("right"):
            sensorLine = <line x1={`${LINELENGTH}`} y1="0" x2="0" y2="0"
                stroke="black" strokeWidth="2" />
            break;
        default:
            sensorLine = null;
    }
    return (
        <>
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
                {sensorLine}
                <circle cx="0" cy="0" r="23" fill={color} stroke="#000" strokeWidth="2" />
                <text
                    x="0"
                    y="2"
                    textAnchor="middle"
                    alignmentBaseline="middle"
                    fontSize={smallInner ? "13" : "16"}
                    fill="#000">
                    {innerText}
                </text>
                <RelativeText
                    dir="right"
                    textDir={textDir}
                    text={outerText}
                    positions={[[0, -34], [32, 2], [0, 38], [-32, 2]]}
                    small
                />
                { loadIfBlank && (innerText == "" || innerText == undefined) &&
                <g transform={`translate(-12,-12)`}>
                    <image href={spinnerUrl} width="24" height="24" />
                </g>
                }
            </g>
        </>
    )
}
