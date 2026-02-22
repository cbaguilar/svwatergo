export function getDirection(angle) {
    // this creates a python-style modulus
    const newAngle = ((angle % 360) + 360) % 360;
    switch (newAngle) {
        case 90:
            return 'down';
        case 180:
            return 'left';
        case 270:
            return 'up';
        case 0:
        default:
            return 'right';
    }
}
