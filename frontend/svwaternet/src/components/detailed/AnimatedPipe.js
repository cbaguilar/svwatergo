import React from 'react';
import { motion } from "framer-motion";
import { DARKBLUECOLOR } from './shared';

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
