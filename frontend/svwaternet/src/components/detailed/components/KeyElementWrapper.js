import React, { useState } from 'react';
import { PumpSymbol } from './PumpSymbol';

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
