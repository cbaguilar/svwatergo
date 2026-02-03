function WaterSystemSelector({choices, selected_system, handle_change}) {
    let ops = choices.map(
            option => <option 
                id={option["value"]} 
                key={option["value"]} 
                value={option["value"]}>{option["label"]}
            </option>
        )

    return (
        <div>
            <select 
                value={selected_system} 
                onChange={handle_change}
                style={{
                    background: "#f4f4f4",
                    borderColor: "#dddddd",
                    color: "black",
                    padding: "5px",
                    borderRadius: "3px"
                }}
            >
                {ops}
            </select>
        </div>
    );
}

export default WaterSystemSelector;


