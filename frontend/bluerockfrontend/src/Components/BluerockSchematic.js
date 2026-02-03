import {
    LIGHTGREYCOLOR, LIGHTBLUECOLOR, BLUECOLOR, WHITECOLOR, GREENCOLOR,
    PINKCOLOR, REDCOLOR, DARKBLUECOLOR,
    titleProps, normalTextProps, smallTextProps,
    getFlowColor, getAngle, getDirection,
    PumpSymbol, SensorIndicator, ValveIndicator, VariableValveIndicator,
    StaticRelativeText, RelativeText, ThreeWayValveIndicator, MultiMediaFilter,
    CheckValve, ArrowPolyLine, ChemicalFeed, SingleFilter, DoubleFilter,
    PressureTank, ROVessel, TextArray, Drain, KeyElementWrapper, Key,
    LiquidFillGaugeWrapper, DevToolsDisplay, AnimatedPipe, RebuiltModal,
    TreatmentSystem, VariablePieValveIndicator
} from "./DetailedDashComponents.jsx"

const get_value_unit_string = (sensor_name, modal_table_dict) => {
    const current_value = modal_table_dict.get(sensor_name, "current_value");
    return `${current_value === undefined ? "" : current_value} `
        + `${modal_table_dict.get(sensor_name, "units")}`;
}

function FeedTankSystem({ md }) {
    return (
        <g>
            {/* svg rectangle in the upper-right corner with class bg-yellow disabled color-palatte */}
            <rect rx="10" x="220" y="10" width="210px" height="250px" fill="#ffcc9c" />
            <text x="240" y="40" {...titleProps}>
                FEED TANK SYSTEM
            </text>
            <AnimatedPipe
                paths={[[[265.5, 214], [265.5, 124], [350.5, 124]]]}
                pipeOn={md.get("wellpumprun", "current_value")}
            />
            <SensorIndicator
                x="370"
                y="79"
                line="down"
                textDir="left"
                innerText={md.get("feedtanklevel", "abbreviated_name")}
                on_click={md.get("feedtanklevel", "on_click")}
                outerText={get_value_unit_string("feedtanklevel", md)}
            />
            <LiquidFillGaugeWrapper
                dir="down" x="385" y="141" text="Feed Tank" textDir="down"
                fillLevel={md.get("feedtanklevel", "current_value")}
            />
            <PumpSymbol
                x="265.5" y="214"
                innerText={md.get("wellpumprun", "abbreviated_name")}
                flow={md.get("wellpumprun", "current_value")}
                on_click={md.get("wellpumprun", "on_click")}
            />
            <SensorIndicator WaterScope x="265.5" y="164" innerText="100" outerText='12345' />
        </g>
    );
}

function ROSystem({ md }) {
    let p1_val = md.get("feedpumprun", "current_value");
    let av1_val = md.get("inletrun", "current_value");
    let p2_val = md.get("ropumprun", "current_value");
    let av2_val = md.get("runflush", "current_value");
    let p3_val = md.get("deliveryrun", "current_value");
    let av5_on = md.get("concbypassrun", "current_value");
    let ft5_on = md.get("concentrateflow", "current_value") > 0;
    let av4_on = md.get("recyclevalveposition", "current_value") > 0;
    let ft3_flowing = md.get("permeateflow", "current_value") > 0;
    let av3_on = md.get("ropressctrlvalveposition", "current_value") > 0;

    let p1_to_av1 = p1_val && av1_val && p2_val;
    let permeate_flush = av2_val && p3_val;
    let permeate_feed_junction_to_p2 = p1_to_av1 || permeate_flush;
    let ro_to_av6 = ft3_flowing && permeate_feed_junction_to_p2;
    let pt4_to_av5 = permeate_feed_junction_to_p2 && av5_on && ft5_on;
    let pt4_to_av3 = permeate_feed_junction_to_p2 && av3_on && ft5_on;
    let pt4_to_av4 = permeate_feed_junction_to_p2 && av4_on;
    let av3_av5_junction = pt4_to_av5 || pt4_to_av3;
    let av6_to_av7 = !md.get("proddiversionrun", "current_value") && ro_to_av6;
    let av6_to_product_tank = md.get("proddiversionrun", "current_value") && ro_to_av6;
    let junction_to_av7 = av6_to_product_tank || av3_av5_junction;
    let to_septic_tank = !md.get("residtankvalverun", "current_value") && junction_to_av7;
    let to_residual_tank = md.get("residtankvalverun", "current_value") && junction_to_av7;

    return (
        <g>
            {/* large light blue rectangle to the right of this that goes lower */}
            <rect rx="10" x="440" y="10" width="670px" height="770px" fill="#d6dce5" />

            <text x="860" y="40"{...titleProps}>REVERSE OSMOSIS SYSTEM</text>
            <text x="200" y="30"{...normalTextProps}></text>
            <text y="55" textAnchor="end" {...smallTextProps}>
                <TextArray
                    textArray={["Permeate", "Flush"]}
                    x="550"
                />
            </text>
            <AnimatedPipe
                stroke={LIGHTBLUECOLOR} paths={[[[697.5, 734.5], [560, 734.5], [560, 618.5]]]}
                pipeOn={av6_to_av7}
            />
            <AnimatedPipe
                stroke={PINKCOLOR} paths={[[[544, 364.5], [544, 342]]]}
                pipeOn={pt4_to_av4}
            />


            <AnimatedPipe
                stroke={LIGHTBLUECOLOR}
                paths={[[[618.5, 61], [693.5, 61]]]}
                pipeOn={permeate_flush}
            />
            <AnimatedPipe
                stroke={LIGHTBLUECOLOR}
                paths={[[[554.5, 61], [581, 61]]]} noarr
                pipeOn={permeate_flush}
            />
            <AnimatedPipe
                noarr paths={[[[507, 161], [547.5, 161]]]}
                pipeOn={p1_to_av1}
            />
            <AnimatedPipe
                paths={[[[585, 161], [775, 161]]]}
                pipeOn={p1_to_av1}
            />
            <AnimatedPipe
                paths={[[[957.5, 161], [1017.5, 161], [1017.5, 261], [487.5, 261], [487.5, 331], [532, 331]]]}
                pipeOn={permeate_feed_junction_to_p2}
            />
            <AnimatedPipe
                paths={[[[863, 161], [886.5, 161]]]}
                junctionPositions={[[863, 161]]}
                pipeOn={permeate_feed_junction_to_p2}
            />
            <AnimatedPipe
                noarr
                paths={[[[840, 161], [863, 161]]]}
                junctionPositions={[[863, 161]]}
                pipeOn={p1_to_av1}
            />
            <AnimatedPipe
                stroke={LIGHTBLUECOLOR}
                paths={[[[733, 61], [863, 61], [863, 150]]]}
                pipeOn={permeate_flush}
            />

            <AnimatedPipe
                paths={[[[416.5, 150], [456.5, 150], [456.5, 160.5], [471, 160.5]]]}
                pipeOn={p1_to_av1}
            />

            <AnimatedPipe
                stroke={PINKCOLOR}
                paths={[[[893.5, 508], [749.5, 508]]]}
                junctionPositions={[[893.5, 508]]}
                pipeOn={pt4_to_av4}
            />
            <AnimatedPipe
                noarr
                stroke={PINKCOLOR}
                paths={[[[689.5, 508], [544, 508], [544, 401.5]]]}
                pipeOn={pt4_to_av4}
            />
            <AnimatedPipe
                stroke={PINKCOLOR} paths={[[[893.5, 460.5], [893.5, 497.5]]]}
                pipeOn={permeate_feed_junction_to_p2}
            />
            <AnimatedPipe
                paths={[[[540.5, 331], [893.5, 331], [893.5, 374.5]]]}
                junctionPositions={[[544, 331]]}
                pipeOn={permeate_feed_junction_to_p2}
                stroke={PINKCOLOR}
            />
            <AnimatedPipe
                stroke={LIGHTBLUECOLOR}
                paths={[[[912.5, 446], [936.5, 446], [936.5, 424], [1027, 424], [1027, 517.5]]]}
                junctionPositions={[[936.5, 424]]}
                pipeOn={ro_to_av6}
            />
            <AnimatedPipe
                stroke={LIGHTBLUECOLOR}
                paths={[[[913.5, 402.5], [937, 402.5], [937, 424]]]}
                pipeOn={ro_to_av6}
                noarr />
            <AnimatedPipe
                stroke={PINKCOLOR}
                paths={[[[894, 577.5], [848.5, 577.5]]]}
                junctionPositions={[[894, 577.5]]}
                pipeOn={pt4_to_av3}
            />
            <AnimatedPipe
                stroke={PINKCOLOR} paths={[[[894, 507.5], [894, 566]]]}
                pipeOn={av3_av5_junction}
            />
            <AnimatedPipe
                stroke={PINKCOLOR}
                paths={[[[654, 607.5], [529.5, 607.5]]]}
                junctionPositions={[[560, 607.5], [654, 607.5]]}
                pipeOn={av3_av5_junction}
            />
            <AnimatedPipe
                noarr
                stroke={PINKCOLOR}
                paths={[[[784, 577.5], [654, 577.5], [654, 607.5]]]}
                pipeOn={pt4_to_av3}
            />
            <AnimatedPipe
                noarr
                pipeOn={pt4_to_av5}
                stroke={PINKCOLOR}
                paths={[[[714, 637.5], [654, 637.5], [654, 607.5]]]} />
            <AnimatedPipe
                stroke={PINKCOLOR}
                paths={[[[894, 577.5], [894, 637.5], [749.5, 637.5]]]}
                pipeOn={pt4_to_av5}
            />
            <AnimatedPipe
                stroke={PINKCOLOR}
                paths={[[[492, 587.5], [492, 507.5], [408.5, 507.5]]]}
                pipeOn={to_residual_tank}
            />
            <AnimatedPipe
                stroke={PINKCOLOR}
                paths={[[[492, 627.5], [492, 670], [312, 670], [312, 690]]]}
                pipeOn={to_septic_tank}
            />
            <AnimatedPipe
                stroke={LIGHTBLUECOLOR}
                paths={[[[1027.5, 540], [1027.5, 680], [817.5, 680], [817.5, 698]]]}
                pipeOn={ro_to_av6}
            />
            <AnimatedPipe
                noarr
                stroke={LIGHTBLUECOLOR}
                paths={[[[810, 733.5], [736, 733.5]]]}
                pipeOn={av6_to_av7}
            />
            <AnimatedPipe
                stroke={LIGHTBLUECOLOR}
                paths={[[[847.5, 733.5], [1147.5, 733.5], [1147.5, 703.5], [1187.5, 703.5]]]}
                pipeOn={av6_to_product_tank}
            />

            <SingleFilter x="660" y="81" innerText1='C' innerText1Large outerText='Carbon Filter' textDir='down' />
            <ValveIndicator
                x="730" y="61"
                innerText={md.get("runflush", "abbreviated_name")}
                flow={md.get("runflush", "current_value")}
                on_click={md.get("runflush", "on_click")}
            />
            <PumpSymbol
                x="498" y="161"
                innerText={md.get("feedpumprun", "abbreviated_name")}
                flow={md.get("feedpumprun", "current_value")}
                on_click={md.get("feedpumprun", "on_click")}
            />
            <CheckValve x="600" y="61" />
            <MultiMediaFilter x="731" y="181"
                textDir='down'
                outerText={<TextArray textArray={["MultiMedia", "Filter (MMF)"]} />} />
            <SensorIndicator
                x="638"
                y="161"
                innerText={md.get("inletpressure", "abbreviated_name")}
                on_click={md.get("inletpressure", "on_click")}
                outerText={get_value_unit_string("inletpressure", md)}
                textDir='down'
            />
            <CheckValve x="566.5" y="159" />
            <ValveIndicator
                x="810" y="161"
                innerText={md.get("inletrun", "abbreviated_name")}
                flow={md.get("inletrun", "current_value")}
                on_click={md.get("inletrun", "on_click")}
            />
            <DoubleFilter
                x="928.5" y="181.5"
                innerText1='20'
                innerText2='mM'
                innerText3='5'
                innerText4='mM'
                outerText='Cartridge Filter'
                outerTextDir='down'
            />
            <SensorIndicator
                x="993.5"
                y="127"
                line="down"
                innerText={md.get("feedpressure", "abbreviated_name")}
                on_click={md.get("feedpressure", "on_click")}
                outerText={get_value_unit_string("feedpressure", md)}
            />
            <SensorIndicator
                x="552.5"
                y="261.5"
                innerText={md.get("feedtds", "abbreviated_name")}
                on_click={md.get("feedtds", "on_click")}
                textDir='up'
                outerText={get_value_unit_string("feedtds", md)}
            />
            {/* <SensorIndicator
                x="632.5" y="261.5" textDir='up'
                innerText={md.get("feedflow", "abbreviated_name")}
                on_click={md.get("feedflow", "on_click")}
                outerText={get_value_unit_string("feedflow", md)}
            /> */}
            <SensorIndicator
                x="650" y="331.5" textDir="down"
                outerText={get_value_unit_string("inletflow", md)}
                innerText={md.get("inletflow", "abbreviated_name")}
                on_click={md.get("inletflow", "on_click")}
            />
            <PumpSymbol
                x="800" y="331.5"
                innerText={md.get("ropumprun", "abbreviated_name")}
                flow={md.get("ropumprun", "current_value")}
                on_click={md.get("ropumprun", "on_click")}
            />
            <ArrowPolyLine stroke="black" points="998,268 998,304 1042.5,304" />
            <ChemicalFeed
                x="1063.5"
                y="287"
                text={<TextArray textArray={["Antiscalant", "Dosing"]} />}
                textDir='down' />
            <ROVessel
                x="843.5"
                y="402.5"
                innerText='RO Vessel 1'
                nubPositions={[[50, -17], [-50, 17]]}
            />
            <ROVessel
                x="843.5"
                y="446"
                innerText='RO Vessel 2'
                nubPositions={[[-50, -17], [50, 17]]}
            />
            <SensorIndicator
                x="854.5" y="296.5" line="down"
                innerText={md.get("ropressure", "abbreviated_name")}
                on_click={md.get("ropressure", "on_click")}
                outerText={get_value_unit_string("ropressure", md)}
            />
            <CheckValve dir="up" x="544.5" y="381.5" />
            <SensorIndicator
                dir="up" x="544.5" y="455"
                innerText={md.get("recycleflow", "abbreviated_name")}
                on_click={md.get("recycleflow", "on_click")}
                outerText={get_value_unit_string("recycleflow", md)}
            />
            <VariablePieValveIndicator
                x="713.5" y="508" textDir='up'
                outerText={
                    `${md.get("recyclevalveposition", "abbreviated_name")} `
                    + `(${md.get("recyclevalveposition", "current_value")}`
                    + `%)`
                }
                percentOpen={md.get("recyclevalveposition", "current_value")}
                on_click={md.get("recyclevalveposition", "on_click")}
            />
            <SensorIndicator
                x="933" y="508" line="left"
                innerText={md.get("concentratepressure", "abbreviated_name")}
                on_click={md.get("concentratepressure", "on_click")}
                outerText={get_value_unit_string("concentratepressure", md)}
            />
            <VariablePieValveIndicator
                x="813" y="578" textDir='up'
                outerText={
                    `${md.get("ropressctrlvalveposition", "abbreviated_name")} `
                    + `(${md.get("ropressctrlvalveposition", "current_value")}`
                    + `%)`
                }
                percentOpen={md.get("ropressctrlvalveposition", "current_value")}
                on_click={md.get("ropressctrlvalveposition", "on_click")}
            />
            <ValveIndicator
                x="713.5" y="636.5"
                innerText={md.get("concbypassrun", "abbreviated_name")}
                flow={md.get("concbypassrun", "current_value")}
                on_click={md.get("concbypassrun", "on_click")}
            />
            <SensorIndicator
                x="610" y="606.5" textDir='up'
                innerText={md.get("concentrateflow", "abbreviated_name")}
                on_click={md.get("concentrateflow", "on_click")}
                outerText={get_value_unit_string("concentrateflow", md)}
            />
            <ThreeWayValveIndicator
                dir="down" x="493" y="607"
                innerText={md.get("residtankvalverun", "abbreviated_name")}
                east={md.get("residtankvalverun", "current_value")}
                north={true}
                west={!md.get("residtankvalverun", "current_value")}
                on_click={md.get("residtankvalverun", "on_click")}
            />
            <LiquidFillGaugeWrapper
                dir="down" x="373" y="497" textDir='down' text='Residual'
                fillLevel={md.get("residualtanklevel", "current_value")}
            />
            <SensorIndicator
                x="372" y="431" line="down" textDir='up'
                innerText={md.get("residualtanklevel", "abbreviated_name")}
                on_click={md.get("residualtanklevel", "on_click")}
                outerText={get_value_unit_string("residualtanklevel", md)}
            />
            <SensorIndicator
                WaterScope x="307" y="525.5" line="right" innerText='400' outerText='12345' textDir='left' />
            <Drain x="312" y="717.5" text="To Septic Tank" textDir="down" />
            <SensorIndicator WaterScope x="492" y="707.5" line="up" innerText='200' textDir='left' outerText='123456' />
            <SensorIndicator
                x="1027.5" y="544.5" textDir='left'
                innerText={md.get("permtemp", "abbreviated_name")}
                on_click={md.get("permtemp", "on_click")}
                outerText={get_value_unit_string("permtemp", md)}
            />
            <SensorIndicator
                x="1027.5" y="594.5" textDir='left'
                innerText={md.get("permeateflow", "abbreviated_name")}
                on_click={md.get("permeateflow", "on_click")}
                outerText={get_value_unit_string("permeateflow", md)}
            />
            <SensorIndicator
                x="1027.5" y="644.5" textDir='left'
                innerText={md.get("permnitrate", "abbreviated_name")}
                on_click={md.get("permnitrate", "on_click")}
                outerText={get_value_unit_string("permnitrate", md)}
            />
            <SensorIndicator
                x="965" y="388.5" line="down" textDir='up'
                innerText={md.get("permtds", "abbreviated_name")}
                on_click={md.get("permtds", "on_click")}
                outerText={get_value_unit_string("permtds", md)}
            />
            <SensorIndicator
                x="1027" y="424" textDir='up'
                innerText={md.get("permeatepressure", "abbreviated_name")}
                on_click={md.get("permeatepressure", "on_click")}
                outerText={get_value_unit_string("permeatepressure", md)}
            />
            <ThreeWayValveIndicator
                x="817" y="734"
                innerText={md.get("proddiversionrun", "abbreviated_name")}
                east={!md.get("proddiversionrun", "current_value")}
                north={true}
                west={md.get("proddiversionrun", "current_value")}
                on_click={md.get("proddiversionrun", "on_click")}
            />
            <CheckValve dir="left" x="717" y="734" />
            {/* <SensorIndicator
                x="902" y="734" textDir='up'
                innerText={md.get("???", "abbreviated_name")}
                on_click={md.get("???", "on_click")}
                outerText='hook'
            />
            <SensorIndicator
                x="972" y="734" textDir='down'
                innerText={md.get("???", "abbreviated_name")}
                on_click={md.get("???", "on_click")}
                outerText='NTP'
            />
            <SensorIndicator
                x="1042" y="734" textDir='up'
                innerText={md.get("???", "abbreviated_name")}
                on_click={md.get("???", "on_click")}
                outerText='FTP'
            /> */}
        </g>
    )
}

function WaterDeliverSystem({ md }) {
    let to_permeate_flush = md.get("runflush", "current_value") && md.get("deliveryrun", "current_value");
    let ft4_to_pressure_tank = md.get("deliveryflow", "current_value") > 0 && md.get("deliveryrun", "current_value");

    let leaving_product_tank = to_permeate_flush || ft4_to_pressure_tank;

    return (
        <g>
            <rect rx="10" x="1120" y="80" width="300px" height="700px" fill="#e2f0d9" />
            <text x="1130" y="110"{...titleProps}>WATER DELIVERY</text>
            <text x="1130" y="130"{...titleProps}>SYSTEM</text>
            <AnimatedPipe
                noarr
                stroke={LIGHTBLUECOLOR}
                paths={[[[1246, 700.5], [1382.5, 700.5], [1382.5, 666.5]]]}
                pipeOn={leaving_product_tank}
            />
            <AnimatedPipe
                noarr
                stroke={LIGHTBLUECOLOR}
                paths={[[[1382, 600.5], [1382, 395.5], [1336.5, 395.5]]]}
                pipeOn={ft4_to_pressure_tank}
            />
            <AnimatedPipe
                noarr
                stroke={LIGHTBLUECOLOR}
                paths={[[[1382, 627.5], [1382, 595]]]}
                pipeOn={leaving_product_tank}
            />
            <AnimatedPipe
                stroke={LIGHTBLUECOLOR}
                paths={[[[1298.5, 395.5], [1262, 395.5]]]}
                pipeOn={ft4_to_pressure_tank}
            />
            <AnimatedPipe
                junctionPositions={[[1382, 595.5]]}
                stroke={LIGHTBLUECOLOR}
                paths={[[[1382, 595.5], [1322, 595.5]]]}
                pipeOn={to_permeate_flush}
            />
            <AnimatedPipe
                stroke={LIGHTBLUECOLOR}
                paths={[[[1232, 395.5], [1169.5, 395.5], [1169.5, 173.5], [1211, 173.5]]]}
                pipeOn={ft4_to_pressure_tank}
            />
            <AnimatedPipe
                stroke={LIGHTBLUECOLOR}
                paths={[[[1251, 173.5], [1329.5, 173.5], [1329.5, 53.5]]]} />

            <LiquidFillGaugeWrapper
                x="1225" y="710" textDir='down'
                text="Product Tank"
            />
            <SensorIndicator
                x="1224" y="644.5" line="down" textDir='up'
                innerText={md.get("prodtanklevel", "abbreviated_name")}
                on_click={md.get("prodtanklevel", "on_click")}
                outerText={get_value_unit_string("prodtanklevel", md)}
            />
            <ArrowPolyLine stroke="black" points="1150.5,695 1150.5,565 1173.5,565" />
            <ChemicalFeed
                x="1194"
                y="544.5"
                text={<TextArray textArray={["Chlorine", "Dosing"]} />} />
            <PumpSymbol
                x="1332"
                y="700.5"
                innerText={md.get("deliveryrun", "abbreviated_name")}
                flow={md.get("deliveryrun", "current_value")}
                on_click={md.get("deliveryrun", "on_click")}
            />
            <CheckValve dir="up" x="1382" y="645.5" />
            <text y="592" textAnchor="end" {...smallTextProps}>
                <TextArray
                    textArray={["Permeate", "Flush"]}
                    x="1310"
                />
            </text>
            <SensorIndicator
                x="1382" y="538.5" textDir='left'
                innerText={md.get("deliveryflow", "abbreviated_name")}
                on_click={md.get("deliveryflow", "on_click")}
                outerText={get_value_unit_string("deliveryflow", md)}
            />
            {/* <SensorIndicator
                x="1382" y="468.5" textDir='left'
                innerText={md.get("???", "abbreviated_name")}
                on_click={md.get("???", "on_click")}
                outerText='PT7'
            /> */}
            <CheckValve dir="left" x="1317.5" y="395.5" />
            <SensorIndicator
                x="1169" y="245.5" textDir='right'
                innerText={md.get("deliverypressure", "abbreviated_name")}
                on_click={md.get("deliverypressure", "on_click")}
                outerText={get_value_unit_string("deliverypressure", md)}
            />
            <MultiMediaFilter x="1237.5" y="425.5" textDir="down" outerText='Remineralizer' />
            <PressureTank x="1239" y="175.5" text='Pressure Tank' textDir='down' />
            <text x="1329" y="38" {...smallTextProps} textAnchor='middle'>
                Water Delivery
            </text>
            <SensorIndicator WaterScope x="1329" y="172.5" innerText="300" outerText="123456" textDir='down' />
        </g>
    )
}


function BluerockSchematic({ md }) {
    return (
        <svg width="100%" height="100%" viewBox="0 0 1205 780">
            <g transform="translate(-215,0)">
                <svg width="1420" height="780" viewBox="0 0 1420 780">
                    <FeedTankSystem md={md} />
                    <WaterDeliverSystem md={md} />
                    <ROSystem md={md} />
                </svg>
            </g>
        </svg>
    )
}

export default BluerockSchematic;