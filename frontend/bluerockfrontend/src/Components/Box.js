function Box({
    contents,
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
        {contents}
    </div>
}

export default Box;
