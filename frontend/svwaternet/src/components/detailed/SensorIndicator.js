import React, { useState } from 'react';
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

    //We need to switch the position of our indicator text box based on the value of the "textPosition" prop
    //If the textPosition is "up", we want to move the text box up by 40px
    //If the textPosition is "down", we want to move the text box down by 40px
    //If the textPosition is "left", we want to move the text box left by 40px
    //If the textPosition is "right", we want to move the text box right by 40px
    const [showModal, setShowModal] = useState(false);
    const handleOpenModal = () => {
        setShowModal(true);
        console.log(showModal)
    };
    const handleCloseModal = () => {
        setShowModal(false);
    };

    const color = WaterScope ? LIGHTGREYCOLOR : BLUECOLOR;

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
    let dummyData = [[1220832000000, 22.56], [1220918400000, 21.67], [1221004800000, 21.66], [1221091200000, 21.81], [1221177600000, 21.28], [1221436800000, 20.05], [1221523200000, 19.98], [1221609600000, 18.26], [1221696000000, 19.16], [1221782400000, 20.13], [1222041600000, 18.72], [1222128000000, 18.12], [1222214400000, 18.39], [1222300800000, 18.85], [1222387200000, 18.32], [1222646400000, 15.04], [1222732800000, 16.24], [1222819200000, 15.59], [1222905600000, 14.3], [1222992000000, 13.87], [1223251200000, 14.02], [1223337600000, 12.74], [1223424000000, 12.83], [1223510400000, 12.68], [1223596800000, 13.8], [1223856000000, 15.75], [1223942400000, 14.87], [1224028800000, 13.99], [1224115200000, 14.56], [1224201600000, 13.91], [1224460800000, 14.06], [1224547200000, 13.07], [1224633600000, 13.84], [1224720000000, 14.03], [1224806400000, 13.77], [1225065600000, 13.16], [1225152000000, 14.27], [1225238400000, 14.94], [1225324800000, 15.86], [1225411200000, 15.37], [1225670400000, 15.28], [1225756800000, 15.86], [1225843200000, 14.76], [1225929600000, 14.16], [1226016000000, 14.03], [1226275200000, 13.7], [1226361600000, 13.54], [1226448000000, 12.87], [1226534400000, 13.78], [1226620800000, 12.89], [1226880000000, 12.59], [1226966400000, 12.84], [1227052800000, 12.33], [1227139200000, 11.5], [1227225600000, 11.8], [1227484800000, 13.28], [1227571200000, 12.97], [1227657600000, 13.57], [1227830400000, 13.24], [1228089600000, 12.7], [1228176000000, 13.21], [1228262400000, 13.7], [1228348800000, 13.06], [1228435200000, 13.43], [1228694400000, 14.25], [1228780800000, 14.29], [1228867200000, 14.03], [1228953600000, 13.57], [1229040000000, 14.04], [1229299200000, 13.54]];

    return (
        <>
            <g transform={transstr} onClick={on_click}>
                {sensorLine}
                <circle cx="0" cy="0" r="20" fill={color} stroke="#000" strokeWidth="2" />
                <text
                    x="0"
                    y="2"
                    textAnchor="middle"
                    alignmentBaseline="middle"
                    fontSize={smallInner ? "14" : "20"}
                    fill="#000">
                    {innerText}
                </text>
                <RelativeText
                    dir="right"
                    textDir={textDir}
                    text={outerText}
                    positions={[[0, -28], [25, 2], [0, 32], [-25, 2]]}
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
