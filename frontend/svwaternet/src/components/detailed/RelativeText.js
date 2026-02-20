import React from 'react';
import { getAngle } from './getAngle';
import { getDirection } from './getDirection';

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
