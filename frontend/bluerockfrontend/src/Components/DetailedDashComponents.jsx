import React, { useEffect, useState, useRef } from 'react';
import { motion } from "framer-motion";

import './OpClock.css';

import {ReactComponent as SpinnerSVG} from "./spinner.svg";

export const PINKCOLOR = "#f03cc3";
export const REDCOLOR = "#ff6363";
export const DARKBLUECOLOR = '#1550a3';
export const GREENCOLOR = "#6ac765";
export const WHITECOLOR = "#ffffff";
export const BLUECOLOR = "#54bbff";
export const LIGHTBLUECOLOR = '#39afcc';
export const LIGHTGREYCOLOR = '#b5b5b5';
export const YELLOWCOLOR = "#ffcf57";
export const PURPLECOLOR = "#b68efa";

export const titleProps = {
    fontSize: "20",
    style: { fontWeight: 'bold' }
}
export const normalTextProps = {
    fontSize: "20",
    alignmentBaseline: "middle"
}

export const smallTextProps = {
    fontSize: "15",
    alignmentBaseline: "middle"
}

export const getFlowColor = (dir_in) => {
    if (dir_in === true) {
        return GREENCOLOR;
    } else if (dir_in === false) {
        return REDCOLOR;
    }
    return WHITECOLOR;
}

export function getAngle(direction) {
    switch (direction) {
        case 'down':
            return 90;
        case 'left':
            return 180;
        case 'up':
            return 270;
        case 'right':
        default:
            return 0;
    }
}

export function getDirection(angle) {
    // this creates a python-style modulus
    const newAngle = ((angle % 360) + 360) % 360;
    switch (newAngle) {
        case 90:
            return 'down';
        case 180:
            return 'left';
        case 270:
            return 'up';
        case 0:
        default:
            return 'right';
    }
}

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
    return (
        <g transform={transstr} onClick={on_click}>
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
                    <SpinnerSVG/>
                </g>
                }
            </g>
        </>
    )
}

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
    const transstr = 'translate(' + x + ',' + y + ') '
        + `rotate(${getAngle(dir)})`
    return (
        <g transform={transstr} onClick={on_click}>
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

const f_svg_ellipse_arc = (([cx, cy], [rx, ry], [t1, Δ], φ) => {
    /* [
    Copyright © 2020 Xah Lee
    Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
    The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
    THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
    URL: SVG Circle Arc http://xahlee.info/js/svg_circle_arc.html
    Version 2019-06-19
    ] */
    const cos = Math.cos;
    const sin = Math.sin;
    const π = Math.PI;
    const f_matrix_times = (([[a, b], [c, d]], [x, y]) => [a * x + b * y, c * x + d * y]);
    const f_rotate_matrix = (x => [[cos(x), -sin(x)], [sin(x), cos(x)]]);
    const f_vec_add = (([a1, a2], [b1, b2]) => [a1 + b1, a2 + b2]);
    /* [
    returns a SVG path element that represent a ellipse.
    cx,cy → center of ellipse
    rx,ry → major minor radius
    t1 → start angle, in radian.
    Δ → angle to sweep, in radian. positive.
    φ → rotation on the whole, in radian
    URL: SVG Circle Arc http://xahlee.info/js/svg_circle_arc.html
    Version 2019-06-19
     ] */
    Δ = Δ % (2 * π);
    const rotMatrix = f_rotate_matrix(φ);
    const [sX, sY] = (f_vec_add(f_matrix_times(rotMatrix, [rx * cos(t1), ry * sin(t1)]), [cx, cy]));
    const [eX, eY] = (f_vec_add(f_matrix_times(rotMatrix, [rx * cos(t1 + Δ), ry * sin(t1 + Δ)]), [cx, cy]));
    const fA = ((Δ > π) ? 1 : 0);
    const fS = ((Δ > 0) ? 1 : 0);
    const path_2wk2r = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path_2wk2r.setAttribute("d", "M " + sX + " " + sY + " A " + [rx, ry, φ / (2 * π) * 360, fA, fS, eX, eY].join(" "));
    return path_2wk2r;
});

export function VariablePieValveIndicator({
    x = 0,
    y = 0,
    percentOpen = 20,
    innerText = "",
    dir = "right",
    outerText = "",
    textDir = "right",
    on_click=()=>{}
}) {
    // Svg valve that is made up of a bowtie shape with a circle in the middle of it
    // it is about the size of a sensor and it has a label in the middle of the circle
    // it is red when the valve is closed and green when it is open
    // it can be oriented horizontally or vertically
    // the text orientation should always be normal
    const transstr = 'translate(' + x + ',' + y + ') '
        + `rotate(${getAngle(dir)})`;
    let PO = percentOpen / 100;
    PO = PO >= 1 ? 0.99999 : PO;
    const arc = f_svg_ellipse_arc([0, 0], [20, 20], [0, PO * Math.PI * 2], 0);
    const arcPath = `M 0 0 L 20 0 ${arc.getAttribute('d')} L 0 0`;
    const openArc = <path d={arcPath} fill={GREENCOLOR} stroke="#000" strokeWidth="2" />;

    return (
        <g>
            <g transform={transstr} onClick={on_click}>
                {/* the bowtie shape made up of two horizontal triangles pointing towards each other */}
                <polygon points="-30,20 -30,-20 30,20 30,-20" fill={LIGHTGREYCOLOR} stroke="#000" strokeWidth="2" />
                <circle cx="0" cy="0" r="20" fill={REDCOLOR} stroke="#000" strokeWidth="2" />
                {openArc}
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

export function VariableValveIndicator({
    x = 0,
    y = 0,
    percentOpen = 20,
    innerText = "",
    dir = "right",
    outerText = "",
    textDir = "right" }) {
    // Svg valve that is made up of a bowtie shape with a circle in the middle of it
    // it is about the size of a sensor and it has a label in the middle of the circle
    // it is red when the valve is closed and green when it is open
    // it can be oriented horizontally or vertically
    // the text orientation should always be normal
    const transstr = 'translate(' + x + ',' + y + ') '
        + `rotate(${getAngle(dir)})`;
    let PO = percentOpen / 100;
    PO = PO >= 1 ? 0.99999 : PO;

    return (
        <g>
            <g transform={transstr}>
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

export function ThreeWayVariablePieValveIndicator({
    x = 0,
    y = 0,
    percentOpen1 = 20,
    percentOpen2 = 60,
    innerText = "",
    dir = "right",
    outerText = "",
    tOutflow = false,
    /* if true, valves will be set to inflow, outflow, inflow */
    textDir = "right" }) {

    // Svg valve that is made up of a bowtie shape with a circle in the middle of it
    // it is about the size of a sensor and it has a label in the middle of the circle
    // it is red when the valve is closed and green when it is open
    // it can be oriented horizontally or vertically
    // the text orientation should always be normal
    const transstr = 'translate(' + x + ',' + y + ') '
        + `rotate(${getAngle(dir)})`;

    const innerDir = tOutflow ? 90 : -45;
    let PO1 = percentOpen1 / 100;
    PO1 = PO1 >= 1 ? 0.9999 : PO1;
    let PO2 = percentOpen2 / 100;
    PO2 = PO2 >= 1 ? 0.9999 : PO2;
    const arc1 = f_svg_ellipse_arc([0, 0], [20, 20], [0, PO1 * Math.PI * 2], 0);
    const arcPath1 = `M 0 0 L 20 0 ${arc1.getAttribute('d')} L 0 0`;
    const openArc1 = <path d={arcPath1} fill={PURPLECOLOR} stroke="#000" strokeWidth="2" />;
    
    const arc2 = f_svg_ellipse_arc([0, 0], [20, 20], [0, PO2 * Math.PI * 2], 0);
    const arcPath2 = `M 0 0 L 20 0 ${arc2.getAttribute('d')} L 0 0`;

    // const openArc2 = arcPath2.includes('NaN')
    //     ? ""
    //     : <path d={arcPath2} fill={YELLOWCOLOR} stroke="#000" strokeWidth="2" />;

    return (
        <g transform={'translate(' + x + ',' + y + ') '}>
            <g transform={`rotate(${getAngle(dir)})`}>
                <polygon
                    points="-30,20 -30,-20 0,0"
                    fill={tOutflow ? PURPLECOLOR : LIGHTGREYCOLOR}
                    stroke="#000"
                    strokeWidth="2" />
                <polygon
                    points="0,0 30,20 30,-20"
                    fill={tOutflow ? YELLOWCOLOR : PURPLECOLOR}
                    stroke="#000"
                    strokeWidth="2" />
                <polygon
                    points="20,-30 -20,-30 0,0"
                    fill={tOutflow ? LIGHTGREYCOLOR : YELLOWCOLOR}
                    stroke="#000"
                    strokeWidth="2" />
                <circle cx="0" cy="0" r="20" fill={REDCOLOR} stroke="#000" strokeWidth="2" />
                <g transform={`rotate(${innerDir})`}>
                    {openArc1}
                    <g transform={`scale(1,-1)`}>
                        {/* {openArc2} */}
                    </g>
                </g>
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

export function ThreeWayVariableValveIndicator({
    x = 0,
    y = 0,
    percentOpen1 = 20,
    percentOpen2 = 60,
    innerText = "",
    dir = "right",
    outerText = "",
    /* if true, valves will be set to inflow, outflow, inflow */
    textDir = "right" }) {

    // Svg valve that is made up of a bowtie shape with a circle in the middle of it
    // it is about the size of a sensor and it has a label in the middle of the circle
    // it is red when the valve is closed and green when it is open
    // it can be oriented horizontally or vertically
    // the text orientation should always be normal
    const transstr = 'translate(' + x + ',' + y + ') '
        + `rotate(${getAngle(dir)})`;

    let PO1 = percentOpen1 / 100;
    PO1 = PO1 >= 1 ? 0.9999 : PO1;
    let PO2 = percentOpen2 / 100;
    PO2 = PO2 >= 1 ? 0.9999 : PO2;

    return (
        <g transform={'translate(' + x + ',' + y + ') '}>
            <g transform={`rotate(${getAngle(dir)})`}>
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

export function StaticRelativeText(props) {
    let xPos = props.x ? props.x : 0;
    let yPos = props.y ? props.y : 0;
    return (
        <g>
            <text
                x={`${xPos}`} y={`${yPos}`}
                transform={`rotate(${-getAngle(props.dir)})`}
                textAnchor="middle"
                alignmentBaseline="middle"
                fontSize="20"
                fill="#000">{props.text}
            </text>
        </g>
    );
}

export function RelativeText({
    positions = [[0, 0]],
    dir = "right",
    text = "",
    textDir = "right",
    small }) {
    /*
    positions = [ upPos, rightPos, downPos, leftPos ]
            ex. [ [50,0],[100,25], [50,50], [0,25] ]
    */

    let updatedPositions = positions.length === 1 ?
        new Array(4).fill(positions[0])
        : positions;

    let position;
    let newTextDir = getDirection(getAngle(textDir) - getAngle(dir));
    switch (newTextDir) {
        case 'up':
            position = updatedPositions[0];
            break;
        case 'down':
            position = updatedPositions[2];
            break;
        case 'left':
            position = updatedPositions[3];
            break;
        case 'right':
        default:
            position = updatedPositions[1];
    };

    let textAnchor = "middle";
    textAnchor = textDir === 'right' ? 'start' : textAnchor;
    textAnchor = textDir === 'left' ? 'end' : textAnchor;

    let fontSize = small ? "15" : "20";

    const transstr = `translate(${position[0]},${position[1]}) `
        + `rotate(${-getAngle(dir)})`;
    return (
        <g>
            <text
                x="0" y="0"
                textAnchor={textAnchor}
                transform={transstr}
                alignmentBaseline="middle"
                fontSize={fontSize}
                strokeWidth="0"
                fill="#000">{text} 
            </text>
        </g>
    );
}

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
    return (
        <g transform={transstr} onClick={on_click}>
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

export function MultiMediaFilter({ x = "0", y = "0", textDir = "right", outerText = "" }) {
    // Looks like a pump, but the circle is replaced with a tall rounded rectangle
    //the label is below the shape
    const transstr = 'translate(' + x + ',' + y + ')';
    return (
        <g transform={transstr}>
            <polygon points="-20,20 0,-20 20,20" fill="#fff" stroke="#000" strokeWidth="2" />
            <rect x="-20" y="-80" width="40" height="100" rx="20" ry="20" fill="#fff" stroke="#000" strokeWidth="2" />
            <RelativeText
                dir="right"
                textDir={textDir}
                text={outerText}
                positions={[[0, -90], [28, -25], [0, 37], [-28, -25]]}
                small
            />
        </g>
    )
}

export function CheckValve({ x = "0", y = "0", dir = "right", textDir = "right", text = "" }) {

    //Long capital N-shaped line with an arrow above it pointing
    //to the right.

    const textPositions = [[20, 0], [51, 21.5], [20, 40], [-11, 21.5]];
    const transstr = 'translate(' + x + ',' + y + ')';
    return (
        <g transform="translate(-19,-21)">
            <g transform={transstr}>
                <g transform={`rotate(${getAngle(dir)}, 18.75, 22.5)`}>
                    {/* <polyline points="0,65 0,25 75,65 75,25" strokeWidth="2" fill="none" stroke="#000" />        
                <polyline points="10,15 65,15" strokeWidth="2" fill="none" stroke="#000" />        
                <polygon  points="60,10 65,15 60,20" strokeWidth="2" fill="black" stroke="#000" /> */}
                    <polyline points="0,32.5 0,12.5 37.5,32.5 37.5,12.5" strokeWidth="2" fill="none" stroke="#000" />
                    <polyline points="5,7.5 32.5,7.5" strokeWidth="2" fill="none" stroke="#000" />
                    <polygon points="30,5 32.5,7.5 30,10" strokeWidth="2" fill="black" stroke="#000" />

                    <RelativeText
                        dir={dir}
                        textDir={textDir}
                        text={text}
                        positions={textPositions}
                    />
                </g>
            </g>
        </g>
    )
}

export function ArrowPolyLine({ points, sx = "0", sy = "0", stroke, prero, postro, concentrate, noarr, junctionPositions = [] }) {
    // this could've been done *much* more elegantly with regex
    const splitPoints = points.split(',').filter(word => word !== "");
    if (splitPoints.length < 3) {
        return (<></>)
    }
    const y1_x2_arr = splitPoints[1].split(' ').filter(word => word !== "");
    const y2_x3_arr = splitPoints[2].split(' ').filter(word => word !== "");

    const x1 = parseFloat(splitPoints[0].trim());
    const y1 = parseFloat(y1_x2_arr[0].trim());
    const x2 = parseFloat(y1_x2_arr[1].trim());
    const y2 = parseFloat(y2_x3_arr[0].trim());

    let angle = 90;
    if (x1 !== x2 || y1 !== y2) {
        angle = x1 <= x2
            ? (Math.atan((y2 - y1) / (x2 - x1)) * 180 / Math.PI) - 90
            : (Math.atan((y2 - y1) / (x2 - x1)) * 180 / Math.PI) + 90;
    }

    // default line color
    let lineStroke = stroke === undefined ? DARKBLUECOLOR : stroke;
    if (prero) {
        lineStroke = DARKBLUECOLOR;
    } else if (postro) {
        lineStroke = LIGHTBLUECOLOR;
    } else if (concentrate) {
        lineStroke = PINKCOLOR;
    }

    const junctions = junctionPositions.map((pos, index) => (
        <circle
            r="5"
            strokeWidth="0"
            cx={`${pos[0]}`}
            cy={`${pos[1]}`}
            fill={lineStroke}
            key={`(${index})${JSON.stringify(pos)}`}
        />
    ));

    return (
        <g transform={`translate(${sx},${sy})`}>
            {junctions}
            {!noarr && <g transform={`translate(${x1},${y1}) rotate(${angle})`}>
                <polygon
                    points="-3,3 0,-3 3,3"
                    fill={lineStroke}
                    stroke={lineStroke}
                    strokeWidth="2" />
            </g>}
            <polyline
                points={points}
                fill="none"
                stroke={lineStroke}
                strokeWidth="2" />
        </g>
    );
}


export function ChemicalFeed({ x = "0", y = "0", textDir = "right", text = "" }) {
    return (
        <g transform={`translate(20,0)`}>
            <g transform={`translate(${x},${y})`}>
                <path d="M0,0 v30 q0,10 -10,10 h-20 q-10,0 -10,-10 v-30 z"
                    fill={YELLOWCOLOR} stroke="black" strokeWidth="2" />
                <rect x="-40" y="-20" width="40" height="20" stroke="black" fill="white"
                    strokeWidth="2" />
                <g transform="translate(-20,-40) rotate(45)">
                    <circle cx="0" cy="0" r="18" stroke="black" fill="white"
                        strokeWidth="2" />
                    <line x1="-18" y1="0" x2="18" y2="0" stroke="black" strokeWidth="2" />
                    <line x1="0" y1="18" x2="0" y2="-18" stroke="black" strokeWidth="2" />
                </g>
                <ArrowPolyLine points="-20,-15 -20,40" stroke="black" />
                <RelativeText
                    dir="right"
                    textDir={textDir}
                    text={text}
                    positions={[[-20, -67], [8, -5], [-20, 55], [-48, -5]]}
                    small
                />
            </g>
        </g>
    )
}

export function SingleFilter({ x = 0, y = 0, outerText = "", textDir = "right", innerText1 = "", innerText2 = "", outerTextLarge, innerText1Large }) {
    const textProps = {
        alignmentBaseline: "middle",
        textAnchor: "middle",
        fontSize: innerText1Large ? "18" : "12",
        strokeWidth: "0",
        fill: "black"
    };

    return (
        <g transform="translate(17.2,-15)">
            <g transform={`translate(${x},${y})`} stroke="black" >
                <path d="M-4.5,0 v30 q0,13 -13,13 h-0 q-13,0 -13,-13 v-30 z" strokeWidth="2" fill="white" />
                <rect x="-35" y="-10" width="35" height="10" strokeWidth="2" fill="white" />
                <text x="-17" y="14" {...textProps}> {innerText1} </text>
                <text x="-17" y="27" {...textProps}> {innerText2} </text>
                <RelativeText
                    textDir={textDir}
                    positions={[[-17, -22], [5, 15], [-17, 55], [-38, 15]]}
                    text={outerText}
                    small={!outerTextLarge} />
            </g>
        </g>

    )
}

export function DoubleFilter({
    x = "0",
    y = "0",
    innerText1 = "",
    innerText2 = "",
    innerText3 = "",
    innerText4 = "",
    outerText = "",
    outerTextDir = "right"
}) {
    return (
        <g transform={`translate(-18,0)`}>
            <g transform={`translate(${x},${y})`}>
                <SingleFilter
                    x="0" y="0"
                    innerText1={innerText1}
                    innerText2={innerText2} />
                <SingleFilter
                    x="35" y="0"
                    innerText1={innerText3}
                    innerText2={innerText4} />
                <rect x="12" y="-24" width="8" height="8" fill="white" />
                <RelativeText
                    textDir={outerTextDir}
                    text={outerText}
                    positions={[[20, -37], [58, 0], [20, 43], [-20, 0]]}
                    small
                />
            </g>
        </g>
    );
}

export function PressureTank({ x = "0", y = "0", text = "", textDir = "right" }) {
    return (
        <g transform={`translate(${x},${y})`}>
            <rect x="-22.5" y="-40" width="45" height="80" rx="10" ry="10" fill="#fff" stroke="#000" strokeWidth="2" />
            <RelativeText
                text={text}
                textDir={textDir}
                positions={[[0, -50], [30, 0], [0, 50], [-30, 0]]}
                small
            />
        </g>
    );
}

export function TreatmentSystem({ x = "0", y = "0", text = "", textDir = "right" }) {
    return (
        <g transform={`translate(${x},${y})`}>
            <rect
                x="-40" y="-20"
                width="80"
                height="40"
                rx="2"
                fill="#fff"
                stroke="#000" strokeWidth="2" />
            <line
                x1="-39" y1="19" x2="39" y2="-19" strokeLinecap='round'
                stroke="black" strokeWidth="2" />
            <RelativeText
                text={text}
                textDir={textDir}
                positions={[[0, -30], [45, 0], [0, 30], [-45, 0]]}
                small
            />
        </g>
    );
}

export function ROVessel({
    x = "0",
    y = "0",
    outerText = "",
    innerText = "",
    textDir = "right",
    dir = "right",
    nubPositions = []
}) {
    // example of nubPositions is [[40,50],[60,40],[40,50]]
    const nubs = nubPositions.map((nubPos, index) =>
        <rect
            width="10"
            height="10"
            stroke="black"
            strokeWidth="2"
            rx="3.5"
            x={`${nubPos[0] - 5}`}
            y={`${nubPos[1] - 5}`}
            fill="white"
            key={`${index}${JSON.stringify(nubPositions)}`}
        />)
    return (
        <g transform={`translate(${x},${y}) rotate(${getAngle(dir)})`}>
            <line
                x1="-70"
                y1="0"
                x2="70"
                y2="0"
                stroke={LIGHTBLUECOLOR}
                strokeWidth="10"
                strokeLinecap="round"
            />
            {nubs}
            <rect x="-65" y="-16" width="130" height="32" rx="10" ry="10" fill="#fff" stroke="#000" strokeWidth="2" />
            <text
                {...titleProps}
                textAnchor='middle'
                x="0"
                y="6"
            >{innerText}</text>
            <RelativeText
                dir={dir}
                text={outerText}
                textDir={textDir}
                positions={[[0, -27], [80, 2], [0, 30], [-80, 2]]}
                small
            />
        </g>
    );
}

export function TextArray({ textArray = [], x = "0", dy = "1.2em" }) {
    const array = textArray.map((text, index) =>
    (<tspan
        x={x}
        dy={index === 0 ? "0" : dy}
        key={`(${index})${JSON.stringify(textArray)}${x}`}>
        {text}
    </tspan>));
    return array;
}

export function Drain({ x = "0", y = "0", text = "", textDir = "right" }) {
    return (
        <g transform={`translate(${x},${y})`}>
            <ArrowPolyLine noarr stroke="black" points="-0.5, 18.5 -0.5, -1.5 -15.5, -16.5 -0.5, -1.5 14.5, -16.5" />
            <RelativeText
                dir="right"
                text={text}
                textDir={textDir}
                positions={[[0, -27], [20, 2], [0, 30], [-20, 2]]}
                small
            />
        </g>
    )
}

export function KeyElementWrapper({ component, x = "0", y = "0", compname = "PumpSymbol", setCCFunc, isOn = false }) {
    const [isHovered, setIsHovered] = useState(false);

    const handleMouseEnter = () => isOn && setIsHovered(true);
    const handleClick = () => isOn && setCCFunc(compname);
    const handleMouseLeave = () => setIsHovered(false);

    return (
        <g
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
            onClick={handleClick}
        >
            <g transform={`translate(${x},${y})`}>
                {component}
                <circle r="20" fill="rgba(0, 0, 0, 0)" /> {/*invisible hitbox*/}
                {isHovered && <circle r="30" fill="none" stroke="red" strokeWidth="5" />}
            </g>
        </g>
    )
}

export function Key() {
    const [isOn, setIsOn] = useState(false);
    const [curComponent, setCurComponent] = useState("");
    const setCC = (compname) => { setCurComponent(compname) };
    return (
        <g>
            <rect rx="10" x="0" y="10" width="210px" height="660px" fill="#e5d6d6" />
            <text x="88" y="40" {...titleProps}>
                KEY
            </text>

            <g transform={`translate(40, 70) scale(0.9)`}>
                <KeyElementWrapper
                    x="10" y="0"
                    component={<SensorIndicator outerText="Sensor" textDir="down" loadIfBlank={false}/>}
                    compname='SensorIndicator'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="70" y="25"
                    component={<SensorIndicator outerText="WaterScope Meter" textDir="down" WaterScope loadIfBlank={false}/>}
                    compname='SensorIndicator WaterScope'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="130" y="0"
                    component={<PumpSymbol outerText="Pump" textDir="down" />}
                    compname='PumpSymbol'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="10" y="100"
                    component={<ValveIndicator outerText="Valve" textDir="down" />}
                    compname='ValveIndicator'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="130" y="100"
                    component={<ThreeWayValveIndicator outerText="3-Way Valve" textDir='down' />}
                    compname='ThreeWayValveIndicator'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="0" y="232"
                    component={<MultiMediaFilter />}
                    compname='MultiMediaFilter'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="0" y="265" textAnchor="middle">
                    MultiMedia
                </text>
                <text {...smallTextProps} x="0" y="280" textAnchor="middle">
                    Filter
                </text>
                <KeyElementWrapper
                    x="70" y="211"
                    component={<ChemicalFeed />}
                    compname='ChemicalFeed'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="70" y="265" textAnchor="middle">
                    Chemical
                </text>
                <text {...smallTextProps} x="70" y="280" textAnchor="middle">
                    Feed
                </text>
                <KeyElementWrapper
                    x="140" y="170"
                    component={<CheckValve />}
                    compname='CheckValve'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="140" y="193" textAnchor="middle">
                    Check Valve
                </text>
                <KeyElementWrapper
                    x="140" y="235"
                    component={<SingleFilter outerText='Filter' textDir="down" />}
                    compname='SingleFilter'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="10" y="320"
                    component={<DoubleFilter />}
                    compname='DoubleFilter'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="10" y="360" textAnchor="middle">
                    Double Filter
                </text>
                <KeyElementWrapper
                    x="110" y="295"
                    component={<AnimatedPipe paths={[[[40, 0], [-40, 0]]]} />}
                    compname='AnimatedPipe'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="110" y="310" textAnchor="middle">
                    Pre RO Pipe
                </text>
                <KeyElementWrapper
                    x="110" y="325"
                    component={<AnimatedPipe stroke={LIGHTBLUECOLOR} paths={[[[40, 0], [-40, 0]]]} />}
                    compname='AnimatedPipe stroke={LIGHTBLUECOLOR}'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="110" y="340" textAnchor="middle">
                    Post RO Pipe
                </text>
                <KeyElementWrapper
                    x="110" y="355"
                    component={<AnimatedPipe stroke={PINKCOLOR} paths={[[[40, 0], [-40, 0]]]} />}
                    compname='AnimatedPipe stroke={PINKCOLOR}'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="110" y="370" textAnchor="middle">
                    Concentrate Pipe
                </text>
                <KeyElementWrapper
                    x="0" y="417"
                    component={<LiquidFillGaugeWrapper />}
                    compname='LiquidFillGaugeWrapper'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="0" y="475" textAnchor="middle">
                    Tank
                </text>
                <KeyElementWrapper
                    x="73" y="425"
                    component={<PressureTank />}
                    compname='PressureTank'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="75" y="475" textAnchor="middle">
                    Pressure Tank
                </text>
                <KeyElementWrapper
                    x="143" y="410"
                    component={<VariableValveIndicator dir="right" />}
                    compname='VariableValveIndicator'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="145" y="445" textAnchor="middle">
                    Variable
                </text>
                <text {...smallTextProps} x="145" y="460" textAnchor="middle">
                    Valve
                </text>
                <KeyElementWrapper
                    x="40" y="510"
                    component={<ROVessel outerText='RO Vessel' textDir='down' />}
                    compname='ROVessel'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="149" y="510"
                    component={<Drain text='Drain' textDir='down' />}
                    compname='Drain'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="9" y="590"
                    component={<ThreeWayVariableValveIndicator
                        outerText={<TextArray textArray={["3-Way", "Variable Valve"]} />}
                        textDir='down'
                    />}
                    compname='ThreeWayVariableValveIndicator'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="110" y="570"
                    component={<ArrowPolyLine stroke={"BLACK"} points="40,0 -40,0" />}
                    compname="ArrowPolyLine stroke='black'"
                    isOn={isOn}
                    setCCFunc={setCC} />
            </g>
            <DevToolsDisplay
                curComponent={curComponent}
                isOn={isOn}
                setIsOn={() => setIsOn((prev) => !prev)} />
        </g>
    )
};

export function LiquidFillGaugeWrapper({ x = "0", y = "0", fillLevel = 50, text = "", textDir = "right" }) {
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
                fill="#68b7fc" 
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

export function DevToolsDisplay({ curComponent, setIsOn, isOn }) {


    const LARGESTEPSIZE = 100;
    const MEDIUMSTEPSIZE = 10;
    const SMALLSTEPSIZE = 0.5;

    const [xPos, setXPos] = useState(300);
    const [yPos, setYPos] = useState(300);
    const [polyArr, setPolyArr] = useState([]);
    const [rot, setRot] = useState(90);

    const xPosRef = useRef(xPos);
    const yPosRef = useRef(yPos);
    let otherProps = "";
    useEffect(() => {
        xPosRef.current = xPos;
        yPosRef.current = yPos;
    }, [xPos, yPos]);

    const changeX = (dx) => {
        setXPos((x) => x + dx);
    };
    const changeY = (dy) => {
        setYPos((y) => y + dy);
    };

    useEffect(() => {
        const handleKeyDown = (event) => {
            switch (event.key) {
                case 'w': changeY(-LARGESTEPSIZE); break;
                case 'a': changeX(-LARGESTEPSIZE); break;
                case 's': changeY(LARGESTEPSIZE); break;
                case 'd': changeX(LARGESTEPSIZE); break;
                case 'i': changeY(-MEDIUMSTEPSIZE); break;
                case 'j': changeX(-MEDIUMSTEPSIZE); break;
                case 'k': changeY(MEDIUMSTEPSIZE); break;
                case 'l': changeX(MEDIUMSTEPSIZE); break;
                case 'I': changeY(-SMALLSTEPSIZE); break;
                case 'J': changeX(-SMALLSTEPSIZE); break;
                case 'K': changeY(SMALLSTEPSIZE); break;
                case 'L': changeX(SMALLSTEPSIZE); break;
                case ' ':
                case 'Enter':
                    setPolyArr((prev) => [...prev, [xPosRef.current, yPosRef.current]]);
                    break;
                case 'z':
                    setPolyArr(prev => {
                        let out = [...prev];
                        out.pop();
                        return out;
                    });
                    break;
                case 'r': setRot(prev => (prev + 90) % 360); break;
                case 'x': setPolyArr([]); break;
                case '`': setIsOn(); break;
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => {
            window.removeEventListener('keydown', handleKeyDown);
        };
    }, []);

    if (!isOn) { return <></> }

    const regex1 = /^ArrowPolyLine/;
    const regex2 = /^AnimatedPipe/;
    let polyline;
    let isPolyline = false;
    let isAnimatedPipe = false;
    let polylineMarker;
    if (regex1.test(curComponent)) {
        isPolyline = true;
        let outstr = "";
        polyArr.map((arr) => { outstr += `${arr[0]},${arr[1]} `; return null });
        outstr += `${xPos},${yPos}`;
        polyline = <>{polyArr.length > 1}<>
            {curComponent === "ArrowPolyLine concentrate" && <ArrowPolyLine concentrate points={outstr} />}
            {curComponent === "ArrowPolyLine prero" && <ArrowPolyLine prero points={outstr} />}
            {curComponent === "ArrowPolyLine postro" && <ArrowPolyLine postro points={outstr} />}
            {curComponent === "ArrowPolyLine stroke='black'" && <ArrowPolyLine stroke="black" points={outstr} />}
        </> </>
        polylineMarker = <circle r="4" x={xPos} y={yPos} fill="rgba(255,0,0,0.5)" />
        otherProps = polyArr.length > 0 ? `points="${outstr}"` : "";
    } else if (regex2.test(curComponent)) {
        isAnimatedPipe = true;
        isPolyline = true;
        let outarr = [];
        polyArr.map((arr) => { outarr.push(arr); return null; });
        outarr.push([xPos, yPos])
        polylineMarker = <circle r="6" x={xPos} y={yPos} fill="rgba(255,0,0,0.5)" />
        polyline = <>{polyArr.length > 1}<>
            {curComponent === "AnimatedPipe" && <AnimatedPipe
                paths={[outarr]} speed={5} stroke={DARKBLUECOLOR} />}
            {curComponent === "AnimatedPipe stroke={LIGHTBLUECOLOR}" && <AnimatedPipe
                paths={[outarr]} speed={5} stroke={LIGHTBLUECOLOR} />}
            {curComponent === "AnimatedPipe stroke={PINKCOLOR}" && <AnimatedPipe
                paths={[outarr]} speed={5} stroke={PINKCOLOR} />}
        </> </>
        otherProps = `paths={[${JSON.stringify(outarr)}]}`;
    }
    return (
        <>
            <g transform={`translate(${xPos},${yPos})`}>
                {curComponent === "DoubleFilter" && <DoubleFilter />}
                {curComponent === "SensorIndicator" &&
                    <>
                        <SensorIndicator line="up" />
                        <SensorIndicator line="right" />
                        <SensorIndicator line="down" />
                        <SensorIndicator line="left" />
                    </>}
                {curComponent === "SensorIndicator WaterScope" &&
                    <>
                        <SensorIndicator WaterScope line="up" />
                        <SensorIndicator WaterScope line="right" />
                        <SensorIndicator WaterScope line="down" />
                        <SensorIndicator WaterScope line="left" />
                    </>}
                {curComponent === "PumpSymbol" && <PumpSymbol />}
                {curComponent === "ValveIndicator" && <ValveIndicator dir={getDirection(rot)} />}
                {curComponent === "ThreeWayValveIndicator" && <ThreeWayValveIndicator dir={getDirection(rot)} />}
                {curComponent === "MultiMediaFilter" && <MultiMediaFilter />}
                {curComponent === "ChemicalFeed" && <ChemicalFeed />}
                {curComponent === "CheckValve" && <CheckValve dir={getDirection(rot)} />}
                {curComponent === "SingleFilter" && <SingleFilter />}
                {curComponent === "DoubleFilter" && <DoubleFilter />}
                {curComponent === "PressureTank" && <PressureTank />}
                {curComponent === "VariableValveIndicator" && <VariableValveIndicator dir={getDirection(rot)} />}
                {curComponent === "LiquidFillGaugeWrapper" && <LiquidFillGaugeWrapper />}
                {curComponent === "Drain" && <Drain />}
                {curComponent === "ROVessel" && <ROVessel dir={getDirection(rot)} />}
                {curComponent === "ThreeWayVariableValveIndicator" && <ThreeWayVariableValveIndicator dir={getDirection(rot)} />}
                {polylineMarker}
            </g>
            {polyline}
            <text x="50" y="760" fontFamily='monospace'>
                {`<${curComponent} ${rot !== 0 ? `dir="${getDirection(rot)}" ` : ""}${isPolyline ? "" : `x="${xPos}" y="${yPos}"`} ${otherProps}/>`}
            </text>
            <text x="50" y="778">
                Large Step (WASD) | Medium Step (IJKL) | Small Step (SHIFT - IJKL)
                | rotate (r) | place polyline node (enter/space)
                | delete polyline (x) | undo polyline node (z)
            </text>
        </>)
}

function getUnitVector(p1 = [10, 10], p2 = [20, 20]) {
    const vector = [p1[0] - p2[0], p1[1] - p2[1]];
    const x = vector[0];
    const y = vector[1];
    const magnitude = Math.sqrt(x * x + y * y);
    if (magnitude === 0) { return [1, 0]; }
    return [x / magnitude, y / magnitude];
}

export function AnimatedPipe({
    paths = [
        [[300, 300], [370, 300], [370, 350]],
        [[350, 300], [350, 200]]],
    speed = 5,
    stroke = DARKBLUECOLOR,
    pipeWidth = -3,
    junctionPositions,
    noarr = false,
    pipeOn = true,
    animated = true
}) {
    let pWidth = pipeWidth + 9;
    let pipeStrings = [];
    let arrows = [];
    for (let i = 0; i < paths.length; i++) {
        let pipeString = "";
        paths[i].map((point) => {
            pipeString += `${point[0]},${point[1]} `
        })
        pipeStrings.push(pipeString);

        if (paths[i].length < 2) {
            arrows.push(null);
            continue;
        }
        const x1 = paths[i][paths[i].length - 1][0];
        const y1 = paths[i][paths[i].length - 1][1];
        const x2 = paths[i][paths[i].length - 2][0];
        const y2 = paths[i][paths[i].length - 2][1];

        if (x1 === x2 && y1 === y2) { continue; }
        if (noarr) { continue; }

        const angle = x1 <= x2
            ? (Math.atan((y2 - y1) / (x2 - x1)) * 180 / Math.PI) - 90
            : (Math.atan((y2 - y1) / (x2 - x1)) * 180 / Math.PI) + 90;
        arrows.push(
            <g
                transform={`translate(${x1},${y1}) rotate(${angle})`}
                key={`pipearrow${i}${JSON.stringify(paths[i])}`}
            >
                <polygon
                    points="-4.5,4.5 0,-4.5 4.5,4.5"
                    fill={stroke}
                    stroke={stroke}
                    strokeWidth="2" />
            </g>
        );
    }

    const junctionPos = junctionPositions === undefined
        ? []
        : junctionPositions;
    const junctions = junctionPos.map((pos, index) =>
        <circle
            r="6"
            strokeWidth="0"
            cx={`${pos[0]}`}
            cy={`${pos[1]}`}
            fill={stroke}
            key={`junction${index}${JSON.stringify(paths)}`}
        />)

    const outerPolylines = pipeStrings.map((pipeString, index) =>
        <polyline
            points={pipeString}
            strokeWidth={pWidth}
            stroke={stroke}
            fill="none"
            key={`(${index})${pipeString}`} />
    );

    const innerDottedPolylines = ! animated ? null : pipeStrings.map((pipeString, index) =>
        // <motion.polyline
        //     points={pipeString}
        //     strokeWidth={pWidth - 3}
        //     stroke="white"
        //     fill="none"
        //     strokeDasharray="3 10"
        //     animate={{
        //         strokeDashoffset: [0, speed === 0 ? 0 : -13]
        //     }}
        //     key={`innerDottedPolyline${index}${JSON.stringify(paths)}`}
        //     transition={{
        //         ease: "linear",
        //         times: [0, 1],
        //         duration: 5 / (speed === 0 ? 1 : speed),
        //         repeat: Infinity,
        //     }}
        // />
        <polyline
            points={pipeString}
            strokeWidth={0}
            stroke="white"
            fill="none"
            key={`innerDottedPolyline${index}${JSON.stringify(paths)}`}
            transition={{
                ease: "linear",
                times: [0, 1],
                duration: 5 / (speed === 0 ? 1 : speed),
                repeat: Infinity,
            }}
        />
    )
    return (
        <>
            <g opacity={ pipeOn ? "1.0" : "0.4" }>
                {junctions}
                {arrows}
                {outerPolylines}
            </g>
            
            
            { pipeOn && innerDottedPolylines}
        </>
    )
}