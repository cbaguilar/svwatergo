import React from 'react';
import { getAngle } from './getAngle';

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
