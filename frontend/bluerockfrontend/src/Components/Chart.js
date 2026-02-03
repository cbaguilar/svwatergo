import * as d3 from "d3";
import { useEffect, useState, useRef } from "react";

const expand_symbol =
    <svg width="800px" height="800px" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M4.75 9.233C4.75 9.64721 5.08579 9.983 5.5 9.983C5.91421 9.983 6.25 9.64721 6.25 9.233H4.75ZM6.25 5.5C6.25 5.08579 5.91421 4.75 5.5 4.75C5.08579 4.75 4.75 5.08579 4.75 5.5H6.25ZM5.5 4.75C5.08579 4.75 4.75 5.08579 4.75 5.5C4.75 5.91421 5.08579 6.25 5.5 6.25V4.75ZM9.233 6.25C9.64721 6.25 9.983 5.91421 9.983 5.5C9.983 5.08579 9.64721 4.75 9.233 4.75V6.25ZM6.03033 4.96967C5.73744 4.67678 5.26256 4.67678 4.96967 4.96967C4.67678 5.26256 4.67678 5.73744 4.96967 6.03033L6.03033 4.96967ZM9.96967 11.0303C10.2626 11.3232 10.7374 11.3232 11.0303 11.0303C11.3232 10.7374 11.3232 10.2626 11.0303 9.96967L9.96967 11.0303ZM15.767 18.75C15.3528 18.75 15.017 19.0858 15.017 19.5C15.017 19.9142 15.3528 20.25 15.767 20.25V18.75ZM19.5 20.25C19.9142 20.25 20.25 19.9142 20.25 19.5C20.25 19.0858 19.9142 18.75 19.5 18.75V20.25ZM18.75 19.5C18.75 19.9142 19.0858 20.25 19.5 20.25C19.9142 20.25 20.25 19.9142 20.25 19.5H18.75ZM20.25 15.767C20.25 15.3528 19.9142 15.017 19.5 15.017C19.0858 15.017 18.75 15.3528 18.75 15.767H20.25ZM18.9697 20.0303C19.2626 20.3232 19.7374 20.3232 20.0303 20.0303C20.3232 19.7374 20.3232 19.2626 20.0303 18.9697L18.9697 20.0303ZM15.0303 13.9697C14.7374 13.6768 14.2626 13.6768 13.9697 13.9697C13.6768 14.2626 13.6768 14.7374 13.9697 15.0303L15.0303 13.9697ZM6.25 15.767C6.25 15.3528 5.91421 15.017 5.5 15.017C5.08579 15.017 4.75 15.3528 4.75 15.767H6.25ZM4.75 19.5C4.75 19.9142 5.08579 20.25 5.5 20.25C5.91421 20.25 6.25 19.9142 6.25 19.5H4.75ZM5.5 18.75C5.08579 18.75 4.75 19.0858 4.75 19.5C4.75 19.9142 5.08579 20.25 5.5 20.25V18.75ZM9.233 20.25C9.64721 20.25 9.983 19.9142 9.983 19.5C9.983 19.0858 9.64721 18.75 9.233 18.75V20.25ZM4.96967 18.9697C4.67678 19.2626 4.67678 19.7374 4.96967 20.0303C5.26256 20.3232 5.73744 20.3232 6.03033 20.0303L4.96967 18.9697ZM11.0303 15.0303C11.3232 14.7374 11.3232 14.2626 11.0303 13.9697C10.7374 13.6768 10.2626 13.6768 9.96967 13.9697L11.0303 15.0303ZM15.767 4.75C15.3528 4.75 15.017 5.08579 15.017 5.5C15.017 5.91421 15.3528 6.25 15.767 6.25V4.75ZM19.5 6.25C19.9142 6.25 20.25 5.91421 20.25 5.5C20.25 5.08579 19.9142 4.75 19.5 4.75V6.25ZM20.25 5.5C20.25 5.08579 19.9142 4.75 19.5 4.75C19.0858 4.75 18.75 5.08579 18.75 5.5H20.25ZM18.75 9.233C18.75 9.64721 19.0858 9.983 19.5 9.983C19.9142 9.983 20.25 9.64721 20.25 9.233H18.75ZM20.0303 6.03033C20.3232 5.73744 20.3232 5.26256 20.0303 4.96967C19.7374 4.67678 19.2626 4.67678 18.9697 4.96967L20.0303 6.03033ZM13.9697 9.96967C13.6768 10.2626 13.6768 10.7374 13.9697 11.0303C14.2626 11.3232 14.7374 11.3232 15.0303 11.0303L13.9697 9.96967ZM6.25 9.233V5.5H4.75V9.233H6.25ZM5.5 6.25H9.233V4.75H5.5V6.25ZM4.96967 6.03033L9.96967 11.0303L11.0303 9.96967L6.03033 4.96967L4.96967 6.03033ZM15.767 20.25H19.5V18.75H15.767V20.25ZM20.25 19.5V15.767H18.75V19.5H20.25ZM20.0303 18.9697L15.0303 13.9697L13.9697 15.0303L18.9697 20.0303L20.0303 18.9697ZM4.75 15.767V19.5H6.25V15.767H4.75ZM5.5 20.25H9.233V18.75H5.5V20.25ZM6.03033 20.0303L11.0303 15.0303L9.96967 13.9697L4.96967 18.9697L6.03033 20.0303ZM15.767 6.25H19.5V4.75H15.767V6.25ZM18.75 5.5V9.233H20.25V5.5H18.75ZM18.9697 4.96967L13.9697 9.96967L15.0303 11.0303L20.0303 6.03033L18.9697 4.96967Z" fill="#000000" />
    </svg>

const get_lowest_time = (data) => data.length >= 1 ? data[0][0] : 0;
const get_highest_time = (data) => data.length >= 1 ? data[data.length - 1][0] : 0;
const get_values = (data) => data.map(d => d[1]);

function binarySearch(array, targetTime) {
    let low = 0;
    let high = array.length - 1;
    let closestLowerIndex = -1;

    while (low <= high) {
        const mid = Math.floor((low + high) / 2);
        const currentTime = array[mid][0];

        if (currentTime === targetTime) return mid;
        else if (currentTime < targetTime) {
            closestLowerIndex = mid;
            low = mid + 1;
        } else high = mid - 1;
    }

    return closestLowerIndex;
}

const BrushChart = ({
    brush_1_time,
    brush_2_time,
    set_brush_1_time,
    set_brush_2_time,
    on_chart_resize = () => { },
    is_loading = false,
    loading_text = "Fetching data from server",
    title = "",
    data = [],
    on_drag = () => {}
}) => {
    const svgRef = useRef();

    const min_time = Math.min(brush_1_time, brush_2_time);
    const max_time = Math.max(brush_1_time, brush_2_time);

    const margin = { top: 40, right: 15, bottom: 35, left: 30 };
    const bottom_height = 60;
    const top_height = 300;
    const middle_margin = 20;
    const body_width = 600;
    const width = body_width + margin.left + margin.right;
    const central_height = bottom_height + top_height + middle_margin;
    let height = bottom_height + top_height + middle_margin + margin.top + margin.bottom;



    useEffect(() => {
        const svg = d3.select(svgRef.current);

        // bottom axis
        let time_to_pos_main = d3
            .scaleTime()
            .domain([min_time, max_time])
            .range([0 + margin.left, body_width + margin.left]);

        let bottomaxis = d3.axisBottom(time_to_pos_main);
        svg.select('#bottomaxis')
            .call(bottomaxis)
            .attr('transform', () => `translate(0,${margin.top + top_height})`)
            .attr("color", "black");


        const main_data_sliced = data
            .slice(
                Math.max(binarySearch(data, min_time), 0),
                Math.min(binarySearch(data, max_time) + 2, data.length)
            );

        try {
            // put in try catch just in case data is empty
            main_data_sliced.unshift([main_data_sliced[0][0], 0]);
            main_data_sliced.push([main_data_sliced[main_data_sliced.length - 1][0], 0]);
        } catch (e) { }

        // left axis
        let leftscale = d3.scaleLinear().domain([Math.max(...get_values(main_data_sliced)), 0]).range([margin.top, top_height + margin.top]);
        let leftaxis = d3.axisLeft(leftscale);
        svg.select('#leftaxis')
            .call(leftaxis.tickFormat(d3.format("d"))) // Ensure ticks are displayed horizontally
            .attr('transform', () => `translate(${margin.left},${0})`)
            .attr("color", "black");

        // full bottom axis
        let time_to_pos_full_scale = d3
            .scaleTime()
            .domain([get_lowest_time(data), get_highest_time(data)])
            .range([margin.left, margin.left + body_width]);

        let fullscaleaxis = d3.axisBottom(time_to_pos_full_scale).ticks(10);
        svg.select('#fullscaleaxis')
            .call(fullscaleaxis)
            .attr('transform', () => `translate(0,${margin.top + central_height})`)
            .attr("color", "black")

        let lineGenerator = d3.line();

        let fullscalescaley =
            d3.scaleLinear()
                .domain([0, Math.max(...get_values(data))])
                .range([margin.top + central_height, margin.top + central_height - bottom_height]);

        const scale_data = data.map(d => [time_to_pos_full_scale(d[0]), fullscalescaley(d[1])])
        scale_data.push([body_width + margin.left, fullscalescaley(0)]);
        scale_data.unshift([margin.left, fullscalescaley(0)]);
        let pathData = lineGenerator(scale_data);
        svg.select('#fullscalearea').attr('d', pathData);

        const scale_main_data = main_data_sliced
            .map(d => [time_to_pos_main(d[0]), leftscale(d[1])]);
        let mainPathDta = lineGenerator(scale_main_data);
        svg.select('#mainarea').attr('d', mainPathDta);

        svg.select('#centerline1')
            .attr('x1', time_to_pos_main((min_time + max_time) / 2))
            .attr('x2', time_to_pos_main((min_time + max_time) / 2))
            .attr('y1', margin.top)
            .attr('y2', margin.top + top_height)
            .attr('stroke', 'white')
            .attr('stroke-width', '4px')

        svg.select('#centerline2')
            .attr('x1', time_to_pos_main((min_time + max_time) / 2))
            .attr('x2', time_to_pos_main((min_time + max_time) / 2))
            .attr('y1', margin.top)
            .attr('y2', margin.top + top_height)
            .attr('stroke', 'red')
            .attr('stroke-width', '2px')

        let brush_spawn_positions = [
            { id: 1, x: time_to_pos_full_scale(brush_1_time), y: margin.top + top_height + middle_margin },
            { id: 2, x: time_to_pos_full_scale(brush_2_time), y: margin.top + top_height + middle_margin }
        ];

        function brush_drag_end(e) {
            if (e.subject.id === 1) {
                let low = Math.min(time_to_pos_full_scale.invert(e.x), brush_2_time);
                let high = Math.max(time_to_pos_full_scale.invert(e.x), brush_2_time);
                on_chart_resize(low, high);
            } else {
                let low = Math.min(time_to_pos_full_scale.invert(e.x), brush_1_time);
                let high = Math.max(time_to_pos_full_scale.invert(e.x), brush_1_time);
                on_chart_resize(low, high);
            }
        }

        let brush_drag = d3.drag()
            .on('end', brush_drag_end)
            .on('drag', handle_brush_drag)
            .on('start', on_drag);

        function handle_brush_drag(e) {
            e.subject.x = e.x;
            if (e.subject.id === 1) set_brush_1_time(time_to_pos_full_scale.invert(e.x));
            else if (e.subject.id === 2) set_brush_2_time(time_to_pos_full_scale.invert(e.x));
        }
        svg.select("#lowerbrusharea")
            .attr("x", time_to_pos_full_scale(min_time))  // x-coordinate
            .attr("y", margin.top + top_height + middle_margin)
            .attr("width", time_to_pos_full_scale(max_time) - time_to_pos_full_scale(min_time))  // width
            .attr("height", 60)  // height
            .attr("fill", "black")  // fill color
            .attr("opacity", 0.10);  // opacity

        function init_brush_drag() {
            svg.selectAll('.brush')
                .call(brush_drag);
        }

        let scroll_spawn_positions = [
            {
                id: 3,
                x: time_to_pos_full_scale(min_time),
                y: margin.top + central_height,
                width: time_to_pos_full_scale(max_time) - time_to_pos_full_scale(min_time)
            }
        ];

        let scrollbar_drag = d3.drag()
            .on('drag', handle_scroll_drag)
            .on('start', on_drag)
            .on('end', scrollbar_drag_end);

        function scrollbar_drag_end(e) {
            on_chart_resize(
                time_to_pos_full_scale.invert(e.x),
                time_to_pos_full_scale.invert(e.x + e.subject.width)
            );
        }

        function handle_scroll_drag(e) {
            e.subject.x = e.x;
            set_brush_1_time(time_to_pos_full_scale.invert(e.x));
            set_brush_2_time(time_to_pos_full_scale.invert(e.x + e.subject.width))
        }

        function init_scrollbar_drag() {
            svg
                .selectAll('.bottomscroll')
                .call(scrollbar_drag)
        }


        function update() {
            let width = 5;
            svg.selectAll('.brush')
                .data(brush_spawn_positions)
                .join('g')
                .attr('transform', function (d) { return `translate(${d.x},${d.y})`; })
                .append('line')
                .attr('x1', 0)
                .attr('x2', 0)
                .attr('y1', 0)
                .attr('y2', bottom_height)
                .attr('stroke', 'black')
                .attr('stroke-width', "2px")
                .attr("stroke-linecap", "round");

            svg.selectAll('.brush')
                .data(brush_spawn_positions)
                .join('g')
                .attr('transform', function (d) { return `translate(${d.x},${d.y})`; })
                .append('rect')
                .attr('x', -2.5)
                .attr('y', bottom_height / 3)
                .attr('width', width)
                .attr('height', bottom_height / 3)
                .attr('fill', "white")
                .attr('rx', 2.5)
                .attr('stroke', 'black')
                .attr('stroke-width', "2px");

            svg.selectAll('.bottomscroll')
                .data(scroll_spawn_positions)
                .join('rect')
                .attr('x', function (d) { return d.x; })
                .attr('y', height - margin.bottom + 20)
                .attr('width', Math.max(time_to_pos_full_scale(max_time) - time_to_pos_full_scale(min_time), 10))
                .attr('height', 10)
                .attr('fill', 'black')
                .attr('opacity', 0.3)
                .attr('rx', 5);
        }

        update();
        init_brush_drag();
        init_scrollbar_drag();

        function handleBrush(e) {
            if (e.selection === null || e.selection[0] === e.selection[1]) { return; }

            svg.select("#selectbrush").remove();
            svg.append("g").attr("id", "selectbrush");
            svg.select("#selectbrush").call(brush);
            let t1 = time_to_pos_main.invert(e.selection[0]);
            let t2 = time_to_pos_main.invert(e.selection[1]);
            set_brush_1_time(t1);
            set_brush_2_time(t2);
            on_chart_resize(t1, t2);
        }

        let brush = d3.brushX()
            .extent([[margin.left, margin.top], [width - margin.right, margin.top + top_height]])
            .on('end', handleBrush);

        if (!is_loading) { svg.select("#selectbrush").call(brush); }
        
    }, [data, brush_1_time, brush_2_time]);


    const [datePart, timePart] = new Date((new Date(brush_1_time).getTime() + new Date(brush_2_time).getTime()) / 2).toLocaleString('en-US', {
        weekday: 'long', // Full day of the week
        year: 'numeric', // Four-digit year
        month: 'long', // Full month name
        day: 'numeric', // Day of the month
        hour: 'numeric', // Hour (24-hour format)
        minute: 'numeric', // Minute
        second: 'numeric', // Second
        timeZoneName: 'short' // Short timezone name (e.g., "EST", "GMT")
    }).split(' at ');
    let current_date_newline = <>
        <tspan x="10" dy="1.2em">{datePart}</tspan>
        <tspan x="10" dy="1.2em">{timePart}</tspan>
    </>

    return (
        <svg
            width={width}
            height={central_height + margin.bottom + margin.top}
            style={{ backgroundColor: "white" }}
            ref={svgRef}
        >
            <path id="mainarea" strokeWidth={1} stroke="black" fill="lightgreen" />
            <rect fill="white" x="0" y="0" width={margin.left} height={height} />
            <rect fill="white" x={width - margin.right} y="0" width={margin.right} height={height} />
            <line id="centerline1" />
            <line id="centerline2" />


            {is_loading && <g>
                <rect
                    x="0"
                    y="0"
                    width={width}
                    height={height}
                    fill="black"
                    opacity="0.3"
                />
                <text
                    x="50%"
                    y="50%"
                    stroke="white"
                    strokeWidth={3}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill="white"
                    fontSize={20}
                    fontWeight="bold">
                    {loading_text}
                </text>
                <text
                    x="50%"
                    y="50%"
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill="black"
                    fontSize={20}
                    fontWeight="bold">
                    {loading_text}
                </text>
            </g>}
            <text x="50%" y="20" textAnchor="middle" fontSize={14}>
                {title}
            </text>
            <rect
                x={width - 46}
                y={8}
                width={39}
                height={15}
                fill="lightgrey"
                rx="4"
                onClick={() => {
                    set_brush_1_time(get_lowest_time(data));
                    set_brush_2_time(get_highest_time(data));
                    on_chart_resize(get_lowest_time(data), get_highest_time(data));
                }}
            />
            <text x={width - 10} y="20" textAnchor="end" fontSize={14} pointerEvents="none">
                reset
            </text>
            <rect
                x={width - 70}
                y={8}
                width={20}
                height={15}
                fill="lightgrey"
                rx="4"
                onClick={() => {
                    let b1 = new Date(min_time).getTime();
                    let b2 = new Date(max_time).getTime();
                    let t1 = (b2 - b1) / 2 + b1;
                    let t2 = (b2 - b1) / 2 + b2;
                    set_brush_1_time(t1);
                    set_brush_2_time(t2);
                    on_chart_resize(t1, t2);
                }}
            />
            <text x={width - 67} y="20" textAnchor="start" fontSize={14} pointerEvents="none">
                ⇥
            </text>
            <rect
                x={width - 94}
                y={8}
                width={20}
                height={15}
                fill="lightgrey"
                rx="4"
                onClick={() => {
                    let b1 = new Date(min_time).getTime();
                    let b2 = new Date(max_time).getTime();
                    let t1 = -(b2 - b1) / 2 + b1;
                    let t2 = -(b2 - b1) / 2 + b2;
                    set_brush_1_time(t1);
                    set_brush_2_time(t2);
                    on_chart_resize(t1, t2);
                }}
            />
            <text x={width - 91} y="20" textAnchor="start" fontSize={14} pointerEvents="none">
                ⇤
            </text>
            <g id="selectbrush" />
            <rect
                x={width - 114}
                y={8}
                width={16}
                height={15}
                fill="lightgrey"
                rx="4"
                onClick={() => {
                    let b1 = new Date(min_time).getTime();
                    let b2 = new Date(max_time).getTime();
                    let t1 = Math.max(-(b2 - b1) / 2 + b1, get_lowest_time(data));
                    let t2 = Math.min((b2 - b1) / 2 + b2, get_highest_time(data));
                    set_brush_1_time(t1);
                    set_brush_2_time(t2);
                    on_chart_resize(t1, t2);
                }}
            />
            <g transform={`translate(${width - 113.4},8) scale(0.018)`} pointerEvents="none">
                {expand_symbol}
            </g>


            <text x={0} y={3} textAnchor="start" fontSize={14} pointerEvents="none">
                {current_date_newline}
            </text>

            <rect 
                x="0" 
                y={margin.top + top_height + middle_margin} 
                width={width}
                height={bottom_height + margin.bottom} 
                fill="white" />
            <path id="fullscalearea" strokeWidth={1} stroke="black" fill="lightblue" />
            <rect id="lowerbrusharea" />
            <g className="brush" />
            <g className="brush" />
            <g id="leftaxis" />
            <g id="fullscaleaxis" />
            <g id="bottomaxis" />
            <rect className="bottomscroll" />
        </svg>
    );
};

export default BrushChart;