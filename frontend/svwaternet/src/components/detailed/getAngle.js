export function getAngle(direction) {
    switch (direction) {
        case 'down':
            return 90;
        case 'left':
            return 180;
        case 'up':
            return 270;
        case 'right':
        default:
            return 0;
    }
}
