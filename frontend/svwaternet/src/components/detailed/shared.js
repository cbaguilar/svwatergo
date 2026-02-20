export const PINKCOLOR = "#f03cc3";
export const REDCOLOR = "#ff6363";
export const DARKBLUECOLOR = '#1550a3';
export const GREENCOLOR = "#6ac765";
export const WHITECOLOR = "#ffffff";
export const BLUECOLOR = "#54bbff";
export const LIGHTBLUECOLOR = '#39afcc';
export const LIGHTGREYCOLOR = '#b5b5b5';
export const YELLOWCOLOR = "#ffcf57";
export const PURPLECOLOR = "#b68efa";

export const titleProps = {
    fontSize: "20",
    style: { fontWeight: 'bold' }
}
export const normalTextProps = {
    fontSize: "20",
    alignmentBaseline: "middle"
}

export const smallTextProps = {
    fontSize: "15",
    alignmentBaseline: "middle"
}

export const getFlowColor = (dir_in) => {
    if (dir_in === true) {
        return GREENCOLOR;
    } else if (dir_in === false) {
        return REDCOLOR;
    }
    return WHITECOLOR;
}
