import { createAsyncThunk, createSlice } from "@reduxjs/toolkit"
import { useDispatch } from 'react-redux';
import { createSelector } from 'reselect';

export const PLAYBACK_HZ = 3;

const CACHE_OVERFLOW_RATIO = 0.5;

const get_min_date = (date_string_1, date_string_2) => {
    return new Date(Math.min(new Date(date_string_1), new Date(date_string_2))).toISOString();
}

export const SYSTEMS = [
    { value: 'santa_teresa', label: 'Santa Teresa' },
    { value: 'bluerock', label: 'Bluerock' },
    { value: 'pryor_farms', label: 'Pryor Farms' },
];

const get_max_date = (date_string_1, date_string_2) => {
    return new Date(Math.max(new Date(date_string_1), new Date(date_string_2))).toISOString();
}

export const binarySearchNearestTime = (arr, targetTime) => {
    let target_time_millis = new Date(targetTime).getTime();
    let left = 0;
    let right = arr.length - 1;
    let nearestIndex = -1;
    let minDiff = Infinity;

    while (left <= right) {
        const mid = Math.floor((left + right) / 2);
        const midTime = new Date(arr[mid]["plctime"]).getTime();
        const diff = Math.abs(midTime - target_time_millis);

        if (diff < minDiff) {
            nearestIndex = mid;
            minDiff = diff;
        }

        if (midTime === target_time_millis) {
            return mid; // Exact match found
        } else if (midTime < target_time_millis) {
            left = mid + 1;
        } else {
            right = mid - 1;
        }
    }
    return nearestIndex;
}


// let host_string = "ec2-54-215-192-153.us-west-1.compute.amazonaws.com:5001";
let host_string = "localhost:5001"

export const initial_page_load = createAsyncThunk(
    'caches/initial_page_load',
    async (amount, { getState }) => {
        const state = getState();
        let [sensor_table, plcrange] = await Promise.all([
            fetch(`http://${host_string}/sensor_info_table/${state.caches.selected_system}`)
                .then(response => response.json()),
            fetch(`http://${host_string}/adaptive_all_history/${state.caches.selected_system}/plctime/${new Date("1970").toISOString()}/${new Date("2100").toISOString()}`)
                .then(response => response.json()),
        ]);

        const sensor_table_dict = {};
        sensor_table.forEach(row => {
            sensor_table_dict[row["internal_data_name"]] = row;
        });

        let end_date = new Date(plcrange[plcrange.length - 1][0]).toISOString(); 

        return {
            sensor_table: sensor_table_dict,
            start_date: new Date(plcrange[0][0]).toISOString(),
            end_date: end_date
        };
    }
)


/*
args: {
    set_selected_sensors_to_loading: bool,
    selected_sensors: ["sensor1", "sensor2", ...]
}
*/
export const update_sensor_list = createAsyncThunk(
    "caches/update_sensor_list",
    async (args, { dispatch, getState }) => {
        let {
            set_selected_sensors_to_loading,
            selected_sensors,
            keep_previous_sensors
        } = args;

        if (set_selected_sensors_to_loading) {
            await dispatch({
                type: "caches/set_selected_sensors_cache_to_loading"
            });
        }

        if (keep_previous_sensors) {
            selected_sensors = Object.keys(state.caches.selected_sensors_cache)
        }

        let state = getState();


        let min_date = new Date(get_min_date(state.caches.handle_1_date, state.caches.handle_2_date)).getTime();
        let max_date = new Date(get_max_date(state.caches.handle_1_date, state.caches.handle_2_date)).getTime();
        let difference = max_date - min_date;

        max_date = new Date(max_date + difference * CACHE_OVERFLOW_RATIO);

        let query_range = {
            start: new Date(min_date).toISOString(),
            end: new Date(max_date).toISOString(),
        };

        await dispatch({
            type: "caches/update_most_recent_query",
            payload: query_range
        });

        let retrieved_sensor_values = await Promise.all(selected_sensors.map(
            sensor_name =>
                fetch(`http://${host_string}/adaptive_all_history/${state.caches.selected_system}/${sensor_name}/${new Date(query_range.start)}/${new Date(query_range.end)}`)
                    .then(response => response.json())
        ));

        state = getState();
        let first_date = get_min_date(state.caches.most_recent_query.start, state.caches.most_recent_query.end);
        let second_date = get_max_date(state.caches.most_recent_query.start, state.caches.most_recent_query.end);

        // if the query range has been updated, during the previous request,then
        // we want to discard the data
        if (first_date != query_range.start || second_date != query_range.end) {
            return;
        }

        await dispatch({
            type: "caches/update_most_recent_completed_query",
            payload: query_range
        });

        let selected_sensors_obj = {};
        for (let i = 0; i < selected_sensors.length; i++) {
            selected_sensors_obj[selected_sensors[i]] = retrieved_sensor_values[i];
        }

        await dispatch({
            type: "caches/set_selected_sensors_cache_to_loaded"
        });

        await dispatch({
            type: "caches/update_selected_sensors_cache",
            payload: selected_sensors_obj
        })
    }
)


// Handles updating the cache displaying values on the schematic 
export const update_playback_cache_async = createAsyncThunk(
    "caches/update_playback_cache",
    async (args, { dispatch, getState }) => {
        let state = getState();

        let width = new Date(state.caches.most_recent_playback_cache_query.end).getTime() - new Date(state.caches.most_recent_playback_cache_query.start).getTime();
        let current_time = new Date((new Date(state.caches.handle_1_date).getTime() + new Date(state.caches.handle_2_date).getTime()) / 2);
        let target_width_size = 300 * get_time_step_size(state.caches.time_step_index);

        // check if last query width is valid
        // if not, run a new query

        let query_range = {
            start: new Date(current_time.getTime() - target_width_size * 0.1).toISOString(),
            end: new Date(current_time.getTime() + target_width_size * 0.9).toISOString()
        };

        if (width > target_width_size * 1.1 || width < target_width_size * 0.9) {
            await dispatch({
                type: "caches/set_playback_cache_state_to_loading"
            });
            await dispatch({
                type: "caches/update_most_recent_playback_cache_query",
                payload: query_range
            })

            let new_cache = await fetch(`http://${host_string}/adaptive_all_sensors/${state.caches.selected_system}/${query_range.start}/${query_range.end}`)
                .then(response => response.json());

            // TODO: need to check if new_cache is still valid

            await dispatch({
                type: "caches/set_playback_cache_state_to_loaded"
            });
            await dispatch({
                type: "caches/update_playback_cache",
                payload: new_cache
            });
            await dispatch({
                type: "caches/update_most_recent_completed_playback_cache_query",
                payload: query_range
            })
            return;
        }


        let eighty_perc_cutoff_completed =
            new Date(
                0.2 * new Date(state.caches.most_recent_completed_playback_cache_query.start).getTime()
                + 0.8 * new Date(state.caches.most_recent_completed_playback_cache_query.end).getTime()
            );

        let five_perc_cutoff_completed =
            new Date(
                0.95 * new Date(state.caches.most_recent_completed_playback_cache_query.start).getTime()
                + 0.05 * new Date(state.caches.most_recent_completed_playback_cache_query.end).getTime()
            );

        let eighty_perc_cutoff =
            new Date(
                0.2 * new Date(state.caches.most_recent_playback_cache_query.start).getTime()
                + 0.8 * new Date(state.caches.most_recent_playback_cache_query.end).getTime()
            )

        let five_perc_cutoff =
            new Date(
                0.95 * new Date(state.caches.most_recent_completed_playback_cache_query.start).getTime()
                + 0.05 * new Date(state.caches.most_recent_completed_playback_cache_query.end).getTime()
            );


        // // if the most recent request is valid, then don't do anything else
        // if (
        //     current_time <= new Date(state.caches.most_recent_completed_playback_cache_query.start)
        //     ||
        //     current_time >= new Date(state.caches.most_recent_completed_playback_cache_query.end)
        // ) {

        // }

        async function handle_playback_cache_request() {
            await dispatch({
                type: "caches/update_most_recent_playback_cache_query",
                payload: query_range
            })

            let state = getState();

            let new_cache = await fetch(`http://${host_string}/adaptive_all_sensors/${state.caches.selected_system}/${query_range.start}/${query_range.end}`)
                .then(response => response.json());

            if (
                query_range.start != state.caches.most_recent_playback_cache_query.start
                ||
                query_range.end != state.caches.most_recent_playback_cache_query.end
            ) {
                return;
            }

            await dispatch({
                type: "caches/update_most_recent_completed_playback_cache_query",
                payload: query_range
            })

            await dispatch({
                type: "caches/update_playback_cache",
                payload: new_cache
            })

            await dispatch({
                type: "caches/set_playback_cache_state_to_loaded"
            });
        }

        // check if time is completely invalid ( < 0 % or >100%)
        // then need to actually wait and load
        if (
            current_time <= new Date(state.caches.most_recent_completed_playback_cache_query.start)
            ||
            current_time >= new Date(state.caches.most_recent_completed_playback_cache_query.end)
        ) {
            // can just return if the last request was valid
            if (!(
                current_time <= five_perc_cutoff
                ||
                current_time >= eighty_perc_cutoff
            )) {
                return;
            }

            await dispatch({
                type: "caches/set_playback_cache_state_to_loading"
            });
            await handle_playback_cache_request();
            return;
        }

        // check to see if cache is close to being exhausted (but not entirely)
        // if so, request a new cache, but don't ask for any loads
        if (
            current_time <= five_perc_cutoff_completed
            ||
            current_time >= eighty_perc_cutoff_completed
        ) {
            // can just return if the last request was valid
            if (!(
                current_time <= five_perc_cutoff
                ||
                current_time >= eighty_perc_cutoff
            )) {
                return;
            }

            await handle_playback_cache_request();
            return;
        }


        // check if time is valid ( > 5% and < 80% )
        // check if last query is valid
        // if not, requery
    }
)

export const handle_time_update = createAsyncThunk(
    "caches/handle_time_update",
    async (args, { dispatch, getState }) => {
        const state = getState();

        let ignore_cache_state = false;
        let increment_time = false;
        
        try {
            ignore_cache_state = args["ignore_cache_state"];
        } catch { };
        try { 
            increment_time = args["increment_time"];
        } catch { };

        if (
            !ignore_cache_state && (
                state.caches.selected_sensors_cache_state != "loaded"
                || state.caches.playback_cache_state != "loaded"
            )
        ) {
            return;
        }

        // check if the sensor range is completely invalid
        // ie, progressing any more will mean that unloaded data will be 
        // visible on the dashboard
        let min_date = new Date(Math.min(new Date(state.caches.handle_1_date), new Date(state.caches.handle_2_date)));
        let max_date = new Date(Math.max(new Date(state.caches.handle_1_date), new Date(state.caches.handle_2_date)));
        if (
            min_date < new Date(state.caches.most_recent_completed_query.start)
            || max_date > new Date(state.caches.most_recent_completed_query.end)
        ) {
            await dispatch(update_sensor_list({
                set_selected_sensors_to_loading: true,
                selected_sensors: Object.keys(state.caches.selected_sensors_cache)
            }));
            // return;
        }

        if (increment_time) {
            await Promise.all([dispatch({ type: "caches/increment_handle_positions" }), dispatch(update_playback_cache_async())]);
        } else {
            dispatch(update_playback_cache_async());
        }

        // Check to see that the most recent query actually could actually be a
        // valid cache range.
        // We check to see that the window width of the last query is roughly
        // the correct size.
        // We also see if the last query's max_range is above half of the 
        // CACHE_OVERFLOW_RATIO, if so, a new request is needed
        let most_recent_query_start = new Date(state.caches.most_recent_query.start);
        let most_recent_query_end = new Date(state.caches.most_recent_query.end);
        let handle_diff = max_date.getTime() - min_date.getTime();
        let timeout_position = new Date((handle_diff * (1 + CACHE_OVERFLOW_RATIO / 2)) + most_recent_query_start.getTime());
        let window_ratio = Math.abs(most_recent_query_end.getTime() - most_recent_query_start.getTime()) / (max_date.getTime() - min_date.getTime());
        if (
            max_date > timeout_position
            || window_ratio < 0.9 + CACHE_OVERFLOW_RATIO
            || window_ratio > 1.1 + CACHE_OVERFLOW_RATIO
            || most_recent_query_start > min_date
        ) {
            await dispatch(update_sensor_list({
                set_selected_sensors_to_loading: false,
                selected_sensors: Object.keys(state.caches.selected_sensors_cache)
            }));
        }

        // TODO: trigger selected sensor list query, but don't set state to loading

        return {};
    }
)

const TIME_STEP_SIZES = [
    [1000 * 60 * 1 / PLAYBACK_HZ, "1 minute a second"],
    [1000 * 60 * 3 / PLAYBACK_HZ, "3 minutes a second"],
    [1000 * 60 * 5 / PLAYBACK_HZ, "5 minutes a second"],
    [1000 * 60 * 10 / PLAYBACK_HZ, "10 minutes a second"],
    [1000 * 60 * 20 / PLAYBACK_HZ, "20 minutes a second"]
]

const get_time_step_size = (idx) => {
    try {
        return TIME_STEP_SIZES[idx][0];
    } catch (e) {
        return TIME_STEP_SIZES[0][0];
    }
}

const get_time_step_name = (idx) => {
    try {
        return TIME_STEP_SIZES[idx][1];
    } catch (e) {
        return TIME_STEP_SIZES[0][1];
    }
}

export const change_to_next_time_step_and_refresh = createAsyncThunk(
    "caches/change_to_next_time_step_and_refresh",
    async (amount, { dispatch, getState }) => {
        await dispatch({ type: "caches/change_to_next_time_step" });
        await dispatch(update_playback_cache_async());
    }
);

export const cachesSlice = createSlice({
    name: "caches",
    initialState: {
        selected_system: localStorage.getItem("current_system") || SYSTEMS[0]["value"],
        playing: false,
        test: "not tested",
        selected_sensors_cache_state: "loading",
        selected_sensors_cache: {},
        playback_cache: [],
        playback_cache_state: "loaded",
        start_date: new Date("1970").toISOString(),
        end_date: new Date("1970").toISOString(),
        handle_1_date: new Date("1970").toISOString(),
        handle_2_date: new Date("1970").toISOString(),
        sensor_table: {},
        time_step_index: 0,
        most_recent_query: {
            start: new Date("1970").toISOString(),
            end: new Date("1970").toISOString()
        },
        most_recent_completed_query: {
            start: new Date("1970").toISOString(),
            end: new Date("1970").toISOString()
        },
        most_recent_playback_cache_query: {
            start: new Date("1970").toISOString(),
            end: new Date("1970").toISOString()
        },
        most_recent_completed_playback_cache_query: {
            start: new Date("1970").toISOString(),
            end: new Date("1970").toISOString()
        },
        selected_downloadable_sensors: ["permtemp"],
        host_string: host_string
    },
    reducers: {
        change_to_next_time_step: (state) => {
            state.time_step_index = (state.time_step_index + 1) % TIME_STEP_SIZES.length;
        },
        update_selected_downloadable_sensors: (state, action) => {
            state.selected_downloadable_sensors = action.payload;
        },
        toggle_playback: (state) => {
            state.playing = !state.playing;
        },
        pause_playback: (state) => {
            state.playing = false;
        },
        set_selected_sensors_cache_to_loading: (state) => {
            state.selected_sensors_cache_state = "loading";
        },
        set_selected_sensors_cache_to_loaded: (state) => {
            state.selected_sensors_cache_state = "loaded";
        },
        set_playback_cache_state_to_loading: (state) => {
            state.playback_cache_state = "loading";
        },
        set_playback_cache_state_to_loaded: (state) => {
            state.playback_cache_state = "loaded";
        },

        update_most_recent_query: (state, action) => {
            let { start, end } = action.payload;

            state.most_recent_query = {
                start: start,
                end: end,
            };
        },
        update_most_recent_completed_query: (state, action) => {
            let { start, end } = action.payload;

            state.most_recent_completed_query = {
                start: start,
                end: end,
            };
        },
        update_most_recent_playback_cache_query: (state, action) => {
            let { start, end } = action.payload;
            state.most_recent_playback_cache_query = {
                start: start,
                end: end
            }
        },
        update_most_recent_completed_playback_cache_query: (state, action) => {
            let { start, end } = action.payload;
            state.most_recent_completed_playback_cache_query = {
                start: start,
                end: end
            }
        },
        update_handle_1_date: (state, action) => {
            state.handle_1_date = action.payload;
        },
        update_handle_2_date: (state, action) => {
            state.handle_2_date = action.payload;
        },
        update_selected_sensors_cache: (state, action) => {
            state.selected_sensors_cache = action.payload;
        },
        increment_handle_positions: (state) => {
            state.handle_1_date = new Date(new Date(state.handle_1_date).getTime() + get_time_step_size(state.time_step_index)).toISOString();
            state.handle_2_date = new Date(new Date(state.handle_2_date).getTime() + get_time_step_size(state.time_step_index)).toISOString();
        },
        update_playback_cache: (state, action) => {
            state.playback_cache = action.payload;
        },
        update_selected_system: (state, action) => {
            state.selected_system = action.payload;
            localStorage.setItem("current_system", action.payload);
            window.location.reload();
        }
    },
    extraReducers: (builder) => {
        builder
            .addCase(initial_page_load.fulfilled, (state, action) => {
                state.start_date = action.payload.start_date;
                state.handle_1_date = action.payload.start_date;
                state.end_date = action.payload.end_date;
                state.handle_2_date = action.payload.end_date;
                state.sensor_table = action.payload.sensor_table;
                console.log(action.payload.sensor_table)
            })
            .addCase(initial_page_load.rejected, () => {
                window.alert("Failed To Contact Server");
            })

            .addCase(update_sensor_list.rejected, (state, error) => {
                console.error(error)
            })

            .addCase(handle_time_update.rejected, (state, error) => {
                console.error(error);
            })
    }
});

export const {
    set_selected_sensors_cache_to_loading,
    set_selected_sensors_cache_to_loaded,
    update_handle_1_date,
    update_handle_2_date,
    toggle_playback,
    update_selected_system,
    pause_playback,
    change_to_next_time_step,
    update_selected_downloadable_sensors
} = cachesSlice.actions;

export const select_selected_sensors_cache_state =
    (state) => state.caches.selected_sensors_cache_state;

export const select_loading = state =>
    state.caches.selected_sensors_cache_state == "loading"
    || state.caches.playback_cache_state == "loading";

export const select_playback_speed = state => get_time_step_size(state.caches.time_step_index);

export const select_playback_speed_name = state => get_time_step_name(state.caches.time_step_index);

const select_sensor_table_state = state => state.caches.sensor_table;

export const select_host_string = state => state.caches.host_string;

export const select_current_system = state => state.caches.selected_system;

export const select_selected_downloadable_sensors = state => state.caches.selected_downloadable_sensors;

// createSelector allows for memoizing
export const select_sensor_table = createSelector(
    [
        select_sensor_table_state,
        state => state.caches.handle_1_date,
        state => state.caches.handle_2_date,
        state => state.caches.playback_cache
    ],
    (sensorTable, handle_1_date, handle_2_date, playback_cache) => {
        let sensor_table = JSON.parse(JSON.stringify(sensorTable));

        sensor_table["get"] = function (sensorname, field) {
            if (this === undefined || this[sensorname] === undefined) {
                return field === "on_click" ? () => { } : "";
            }
            return this[sensorname][field];
        }

        let current_time = (new Date(handle_1_date).getTime() + new Date(handle_2_date).getTime()) / 2;
        let curr_idx = binarySearchNearestTime(playback_cache, current_time);

        Object.keys(sensor_table).forEach(
            key => {
                sensor_table[key]["on_click"] = () => { }
                try {
                    sensor_table[key]["current_value"] = playback_cache[curr_idx][key];
                } catch (e) {
                    sensor_table[key]["current_value"] = undefined;
                }
            }
        );


        return sensor_table;
    }
);


export const select_user_selected_sensors = createSelector([
    state => state.caches.selected_sensors_cache
], (selected_sensor_cache) => new Set(Object.keys(selected_sensor_cache)));

export default cachesSlice.reducer;