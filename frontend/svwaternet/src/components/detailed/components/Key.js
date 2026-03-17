import React, { useState } from 'react';
import { LIGHTBLUECOLOR, PINKCOLOR, smallTextProps, titleProps } from './shared';
import { AnimatedPipe } from './AnimatedPipe';
import { ArrowPolyLine } from './ArrowPolyLine';
import { CheckValve } from './CheckValve';
import { ChemicalFeed } from './ChemicalFeed';
import { DevToolsDisplay } from './DevToolsDisplay';
import { DoubleFilter } from './DoubleFilter';
import { Drain } from './Drain';
import { KeyElementWrapper } from './KeyElementWrapper';
import { LiquidFillGaugeWrapper } from './LiquidFillGaugeWrapper';
import { MultiMediaFilter } from './MultiMediaFilter';
import { PressureTank } from './PressureTank';
import { PumpSymbol } from './PumpSymbol';
import { ROVessel } from './ROVessel';
import { SensorIndicator } from './SensorIndicator';
import { SingleFilter } from './SingleFilter';
import { TextArray } from './TextArray';
import { ThreeWayValveIndicator } from './ThreeWayValveIndicator';
import { ThreeWayVariableValveIndicator } from './ThreeWayVariableValveIndicator';
import { ValveIndicator } from './ValveIndicator';
import { VariableValveIndicator } from './VariableValveIndicator';

export function Key() {
    const [isOn, setIsOn] = useState(false);
    const [curComponent, setCurComponent] = useState("");
    const setCC = (compname) => { setCurComponent(compname) };
    return (
        <g>
            <rect rx="10" x="8" y="8" width="384px" height="484px" fill="#e5d6d6" />
            <text x="200" y="38" {...titleProps} textAnchor="middle">
                KEY
            </text>

            <g transform={`translate(44, 50) scale(0.64)`}>
                <KeyElementWrapper
                    x="48" y="0"
                    component={<SensorIndicator outerText="Sensor" textDir="down" loadIfBlank={false}/>}
                    compname='SensorIndicator'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="244" y="14"
                    component={<SensorIndicator outerText="WaterScope Meter" textDir="down" WaterScope loadIfBlank={false}/>}
                    compname='SensorIndicator WaterScope'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="411" y="0"
                    component={<PumpSymbol outerText="Pump" textDir="down" />}
                    compname='PumpSymbol'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="48" y="102"
                    component={<ValveIndicator outerText="Valve" textDir="down" />}
                    compname='ValveIndicator'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="411" y="118"
                    component={<ThreeWayValveIndicator />}
                    compname='ThreeWayValveIndicator'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="411" y="162" textAnchor="middle">
                    3-Way Valve
                </text>
                <KeyElementWrapper
                    x="48" y="278"
                    component={<MultiMediaFilter />}
                    compname='MultiMediaFilter'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="50" y="308" textAnchor="middle">
                    MultiMedia
                </text>
                <text {...smallTextProps} x="50" y="323" textAnchor="middle">
                    Filter
                </text>
                <KeyElementWrapper
                    x="244" y="214"
                    component={<ChemicalFeed text={<TextArray textArray={["Chemical", "Feed"]} />} textDir="down" />}
                    compname='ChemicalFeed'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="411" y="226"
                    component={<CheckValve />}
                    compname='CheckValve'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="427" y="252" textAnchor="middle">
                    Check Valve
                </text>
                <KeyElementWrapper
                    x="411" y="294"
                    component={<SingleFilter outerText='Filter' textDir="down" />}
                    compname='SingleFilter'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="48" y="390"
                    component={<DoubleFilter />}
                    compname='DoubleFilter'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="52" y="424" textAnchor="middle">
                    Double Filter
                </text>
                <KeyElementWrapper
                    x="244" y="346"
                    component={<AnimatedPipe paths={[[[40, 0], [-40, 0]]]} />}
                    compname='AnimatedPipe'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="244" y="362" textAnchor="middle">
                    Pre RO Pipe
                </text>
                <KeyElementWrapper
                    x="244" y="380"
                    component={<AnimatedPipe stroke={LIGHTBLUECOLOR} paths={[[[40, 0], [-40, 0]]]} />}
                    compname='AnimatedPipe stroke={LIGHTBLUECOLOR}'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="244" y="396" textAnchor="middle">
                    Post RO Pipe
                </text>
                <KeyElementWrapper
                    x="244" y="414"
                    component={<AnimatedPipe stroke={PINKCOLOR} paths={[[[40, 0], [-40, 0]]]} />}
                    compname='AnimatedPipe stroke={PINKCOLOR}'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="244" y="430" textAnchor="middle">
                    Concentrate Pipe
                </text>
                <KeyElementWrapper
                    x="40" y="540"
                    component={<LiquidFillGaugeWrapper />}
                    compname='LiquidFillGaugeWrapper'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="40" y="594" textAnchor="middle">
                    Tank
                </text>
                <KeyElementWrapper
                    x="244" y="500"
                    component={<PressureTank text="Pressure Tank" textDir="down" />}
                    compname='PressureTank'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="411" y="420"
                    component={<VariableValveIndicator dir="right" />}
                    compname='VariableValveIndicator'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <text {...smallTextProps} x="411" y="456" textAnchor="middle">
                    Variable
                </text>
                <text {...smallTextProps} x="411" y="471" textAnchor="middle">
                    Valve
                </text>
                <KeyElementWrapper
                    x="244" y="640"
                    component={<ROVessel outerText='RO Vessel' textDir='down' />}
                    compname='ROVessel'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="411" y="590"
                    component={<Drain text='Drain' textDir='down' />}
                    compname='Drain'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="411" y="530"
                    component={<ThreeWayVariableValveIndicator
                        outerText={<TextArray textArray={["3-Way", "Variable Valve"]} />}
                        textDir='down'
                    />}
                    compname='ThreeWayVariableValveIndicator'
                    isOn={isOn}
                    setCCFunc={setCC} />
                <KeyElementWrapper
                    x="411" y="650"
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
