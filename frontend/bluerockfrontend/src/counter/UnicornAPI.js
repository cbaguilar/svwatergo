
export function getUnicorn() {
    return new Promise((resolve) =>
        setTimeout(() => resolve({ data: "🦄"}), 3000)
    );
}
