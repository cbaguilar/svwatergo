import Highcharts, { chart } from 'highcharts/highstock';
import { useEffect, useRef } from 'react';


export default function StockTicker({
  data,
  title = "No Title",
  upon_window_resize = () => { },
  min_value = 0,
  max_value = 10,
  set_min_value = () => { },
  set_max_value = () => { },
  is_loading = false,
  allow_user_updates = true,
}) {


  const reformatted_title = title || "";
  const min_value_millis = new Date(min_value).getTime();
  const max_value_millis = new Date(max_value).getTime();

  const chartRef = useRef(null);
  const containerRef = useRef(null);
  const colors = Highcharts.getOptions().colors;

  let unicode_value_total = 0;
  for (let i = 0; i < reformatted_title.length; i++) {
    unicode_value_total += reformatted_title.codePointAt(i);
  }
  const color = colors[unicode_value_total % 8];

  let redrawn_data;
  let min_time;
  let max_time;
  try {
    min_time = data[0][0];
    max_time = data[data.length - 1][0];
    const time_diff = max_time - min_time;
    const start_1 = [min_time - time_diff / 2, 0]
    const start_2 = [min_time - 1, data[0][1]]
    const end_1 = [max_time + 1, data[data.length - 1][1]]
    const end_2 = [max_time + time_diff / 2, 0]
    redrawn_data = [start_1, start_2].concat(data, [end_1, end_2]);
  } catch {
    redrawn_data = data;
    min_time = 0;
    max_time = 0;
  }

  try {
    if (redrawn_data[2][1] === true || redrawn_data[2][1] === false) {
      const newly_rewdrawn_data = redrawn_data.map(value => [value[0], Number(value[1])])
      redrawn_data = newly_rewdrawn_data;
    }
  } catch {}

  const on_nav_movement = (e) => {
    // App crashes if operating on wrong trigger type
    if (e.triggerOp != "navigator-drag" && e.trigger != 'zoom') {
      setAxisExtremes(min_value_millis, max_value_millis);
      return;
    }
    upon_window_resize(e.min, e.max, chartRef);
    set_min_value(new Date(e.min));
    set_max_value(new Date(e.max));
  }

  useEffect(() => {
    // Initialize the chart
    const options = {
      title: {
        text: reformatted_title
      },
      chart: {
        type: 'area',
        animation: false,
        panning: {
          enabled: false,
        },
        zooming: {
          type: 'x'
        },
      },
      series: [{
        data: redrawn_data,
        zones: [
          {
            value: min_time,
            color: 'white',
          },
          {
            value: max_time,
            color: color,
          },
          {
            color: 'white'
          }
        ],
        zoneAxis: 'x',
        animation: false
      }],
      navigator: {
        xAxis: {
          floor: Math.min(min_value_millis, min_time),
          ceiling: Math.max(max_value_millis, max_time)
        }
      },

      scrollbar: {
        liveRedraw: false
      },

      rangeSelector: {
        selected: 1
      },

      xAxis: {
        events: {
          afterSetExtremes: on_nav_movement
        },
        ordinal: false,
        plotLines: [{
          color: '#FF0000', // Red
          width: 2,
          value: (min_value_millis + max_value_millis) / 2
        }]
      },
      yAxis: {
        softMin: 0
      },
    };

    if (containerRef.current) {
      chartRef.current = Highcharts.stockChart(containerRef.current, options);
    }

    setAxisExtremes(min_value_millis, max_value_millis);

    // Cleanup function to destroy chart on unmount
    return () => {
      if (chartRef.current) {
        chartRef.current.destroy();
      }
    };
  }, [min_value_millis, max_value_millis]);

  useEffect(() => {
    // Update the chart data whenever the data prop changes
    if (chartRef.current) {
      chartRef.current.series[0].setData(redrawn_data, false); // Update series data without animation
      chartRef.current.redraw(); // Redraw the chart

    }
  }, [data, min_value_millis, max_value_millis]); // Depend on data prop

  const setAxisExtremes = (min, max) => {
    if (chartRef.current) {
      chartRef.current.xAxis[0].setExtremes(min, max);
    }
  };

  return (
    <div style={{ position: "relative" }}>
      {is_loading && (
        <div
          style={{
            position: 'absolute',
            width: '100%',
            height: '100%',
            backgroundColor: 'rgba(200, 200, 200, 0.5)', // Semi-transparent overlay
            zIndex: 999, // Ensure it covers the chart
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            fontSize: '20px',
            color: 'black',
            fontWeight: 'bold',
          }}
        >
          Loading...
        </div>
      )}
      <div ref={containerRef} style={{ height: '100%', width: '100%' }}></div>
    </div>
  );
}

