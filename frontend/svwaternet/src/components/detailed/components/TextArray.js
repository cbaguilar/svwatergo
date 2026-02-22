import React from 'react';

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
