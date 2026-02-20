import React, { useEffect, useRef, useState } from 'react';
import { DARKBLUECOLOR, LIGHTBLUECOLOR, PINKCOLOR } from './shared';
import { AnimatedPipe } from './AnimatedPipe';
import { ArrowPolyLine } from './ArrowPolyLine';
import { CheckValve } from './CheckValve';
import { ChemicalFeed } from './ChemicalFeed';
import { DoubleFilter } from './DoubleFilter';
import { Drain } from './Drain';
import { LiquidFillGaugeWrapper } from './LiquidFillGaugeWrapper';
import { MultiMediaFilter } from './MultiMediaFilter';
import { PressureTank } from './PressureTank';
import { PumpSymbol } from './PumpSymbol';
import { ROVessel } from './ROVessel';
import { SensorIndicator } from './SensorIndicator';
import { SingleFilter } from './SingleFilter';
import { ThreeWayValveIndicator } from './ThreeWayValveIndicator';
import { ThreeWayVariableValveIndicator } from './ThreeWayVariableValveIndicator';
import { ValveIndicator } from './ValveIndicator';
import { VariableValveIndicator } from './VariableValveIndicator';
import { getDirection } from './getDirection';

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
