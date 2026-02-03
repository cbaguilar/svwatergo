import React, { useState } from 'react';
import { Table, Input } from "antd";
import './searchabletable.css'


const SearchableTable = ({ data, columns, filterable_columns=[] }) => {
    const [searchTerm, setSearchTerm] = useState('');
    let filteredData
    if (filterable_columns.length !== 0) {
        filteredData = data.filter((entry) =>
            filterable_columns.reduce((acc, key) => {
                return acc || entry[key].toLowerCase().includes(searchTerm.toLowerCase());
            }, false)
        );
    } else {
        filteredData = data;
    }

    return (
        <div>
            <Input
                placeholder="Search..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                style={{ marginBottom: 16, width: "100%" }}
            />

            <Table 
                rowClassName="custom-row"
                dataSource={filteredData} 
                columns={columns} />
        </div>
    );
};

export default SearchableTable;