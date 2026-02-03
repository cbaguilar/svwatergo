import { useState, useEffect } from 'react';
import {Box} from 'adminlte-2-react';
import { useSelector } from 'react-redux';


function getWindowDimensions() {
    const { innerWidth: width, innerHeight: height } = window;
    return {
        width,
        height
    };
}

export function useWindowDimensions() {
    const [windowDimensions, setWindowDimensions] = useState(getWindowDimensions());

    useEffect(() => {
        function handleResize() {
            setWindowDimensions(getWindowDimensions());
        }

        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
    }, []);

    return windowDimensions;
}


export const CenteredBox = (props) => {
    return <Box style={{maxWidth: '1000px', margin: 'auto'}} {...props} />;
}

export function PrettyBox({
    children,
    topColor="#54b8ff",
    width="100%",
    height=undefined,
    title=undefined
}) {
    return <div style={{
        borderTop: `4px ${topColor} solid`,
        padding: "10px",
        margin: "10px",
        background: "white",
        borderRadius: "5px",
        height: height,
        boxShadow: "0px 0px 17px 1px rgba(0,0,0,0.32)",
        flex: 1,
        width: width
    }}>
        {title && <div style={{fontSize: "2rem"}}>{title}</div>}
        {children}
    </div>
}


const convertToCSV = (data) => {
    // Extract column headers
    const headers = Object.keys(data[0]);

    // Create CSV content
    const csvContent = [
        headers.join(','), // CSV header
        ...data.map(item => headers.map(header => item[header]).join(',')) // CSV rows
    ].join('\n');

    return csvContent;
};


export async function Download_selected_sensors(
    start_date,
    end_date,
    selected_sensors,
    host_string,
    selected_system
) {


    if (selected_sensors.length === 0) {
        window.confirm("Please select sensors to download");
        return;
    }
    if (end_date <= start_date) {
        window.confirm("Invalid date selection");
        return;
    }

    const query_string = `http://${host_string}/specific_sensors_range/${selected_system}/${selected_sensors}/${start_date}/${end_date}`

    let response = await fetch(query_string);
    let response_json = await response.json();

    try {
        const csv = convertToCSV(response_json);
        const blob = new Blob([csv], { type: 'text/csv' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = 'data.csv';
        link.click();
    } catch {
        window.alert("Something went wrong, possibly an invalid range was selected")
    }
}
