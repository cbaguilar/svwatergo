import React from 'react';
import spinnerUrl from "./spinner.svg";
import { BLUECOLOR, LIGHTGREYCOLOR, isHandlerSelected, isModelKeySelected } from './shared';
import { RelativeText } from './RelativeText';

export function SensorIndicator({
    x = "0",
    y = "0",
    innerText = null,
    outerText = null,
    sensorKey = "",
    md = null,
    line = null,
    textDir = "right",
    smallInner = false,
    WaterScope = false,
    loadIfBlank = true,
    on_click = null
}) {
    // svg sensor indicator, circle about the size of a pump with a small label in the middle
    // it has a red border if the sensor is not working
    // it also has a small numerical indicator either above, below, or to either side
    // of the circle with the value of the sensor and its unit
    const transstr = 'translate(' + x + ',' + y + ')';

    const color = WaterScope ? LIGHTGREYCOLOR : BLUECOLOR;
    const resolvedOnClick = (() => {
        if (typeof on_click === 'function') return on_click;
        if (!sensorKey || !md || typeof md.get !== 'function') return () => {};
        const fromModel = md.get(sensorKey, "on_click");
        return typeof fromModel === 'function' ? fromModel : () => {};
    })();
    const handleActivate = (event) => {
        resolvedOnClick(event);
    };
    const isSelected = isModelKeySelected(md, sensorKey) || isHandlerSelected(resolvedOnClick);
    const interactiveStyle = isSelected
        ? {
            cursor: 'pointer',
            filter: 'drop-shadow(0 0 4px rgba(255,32,32,0.95)) drop-shadow(0 0 10px rgba(255,0,0,0.90))',
        }
        : { cursor: 'pointer' };

    const LINELENGTH = 35;
    let sensorLine;
    const computedOuterText = (() => {
        if (outerText !== null && outerText !== undefined) return outerText;
        if (!sensorKey || !md || typeof md.get !== 'function') return "";
        const currentValue = md.get(sensorKey, "current_value");
        const units = md.get(sensorKey, "units");
        if (currentValue === undefined || currentValue === null || currentValue === "") return "";
        const formattedValue =
            typeof currentValue === 'number' && Number.isFinite(currentValue)
                ? currentValue.toLocaleString(undefined, {
                    minimumFractionDigits: 0,
                    maximumFractionDigits: 2,
                })
                : currentValue;
        return `${formattedValue}${units ? ` ${units}` : ""}`;
    })();
    const computedInnerText = (() => {
        if (innerText !== null && innerText !== undefined) return innerText;
        if (!sensorKey || !md || typeof md.get !== 'function') return "";
        return md.get(sensorKey, "abbreviated_name") || "";
    })();




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
                        handleActivate(e);
                    }
                }}
                tabIndex={0}
                role="button"
                style={interactiveStyle}
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
                    {computedInnerText}
                </text>
                <RelativeText
                    dir="right"
                    textDir={textDir}
                    text={computedOuterText}
                    positions={[[0, -34], [32, 2], [0, 38], [-32, 2]]}
                    small
                />
                { loadIfBlank && (computedInnerText === "" || computedInnerText === undefined) &&
                <g transform={`translate(-12,-12)`}>
                    <image href={spinnerUrl} width="24" height="24" />
                </g>
                }
            </g>
        </>
    )
}
