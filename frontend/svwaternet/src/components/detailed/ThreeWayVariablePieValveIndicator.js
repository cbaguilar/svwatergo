import React from 'react';
import { LIGHTGREYCOLOR, PURPLECOLOR, REDCOLOR, YELLOWCOLOR } from './shared';
import { RelativeText } from './RelativeText';
import { StaticRelativeText } from './StaticRelativeText';
import { getAngle } from './getAngle';

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
    const handleActivate = (event) => {
        on_click(event);
    };

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
            <g
                transform={`rotate(${getAngle(dir)})`}
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
