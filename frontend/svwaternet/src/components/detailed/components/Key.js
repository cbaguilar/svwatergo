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
