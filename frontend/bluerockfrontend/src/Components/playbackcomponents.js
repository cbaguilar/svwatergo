export function SinglePlay() {
    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 130 100"
        >
            <path d="M30 10L30 90 110 50z"></path>
        </svg>
    );
}


export function DoublePlay() {
    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="20 0 160 100"
        >
            <path d="M30 10L30 90 110 50z"></path>
            <path d="M90 10L90 90 170 50z"></path>
        </svg>
    );
}

export function Pause() {
    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 100 100"
        >
            <path d="M25 20H45V80H25z"></path>
            <path d="M55 20H75V80H55z"></path>
        </svg>
    );
}

export function SkipSmall() {
    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 130 100"
        >
            <path d="M30 10L30 90 110 50z"></path>
            <path d="M100 10H115V90H100z"></path>
        </svg>
    );
}

export function SkipSmallLeft() {
    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 130 100"
        >
            <path d="M110 10L110 90 30 50z"></path> {/* Triangle pointing left */}
            <path d="M15 10H30V90H15z"></path> {/* Rectangle on the left */}
        </svg>
    );
}

export function SkipLarge() {
    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="20 0 170 100"
        >
            <path d="M30 10L30 90 110 50z"></path>
            <path d="M90 10L90 90 170 50z"></path>
            <path d="M160 10H175V90H160z"></path>
        </svg>
    );
}

export function SkipLargeLeft() {
    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 170 100"
        >
            <path d="M110 10L110 90 30 50z"></path> {/* First triangle pointing left */}
            <path d="M170 10L170 90 90 50z"></path>
            <path d="M15 10H30V90H15z"></path> {/* Rectangle on the left */}
        </svg>
    );
}

export function ZoomOut() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      fill="#000"
      version="1.1"
      viewBox="0 0 512 512"
      xmlSpace="preserve"
    >
      <path d="M497.938 430.063l-112-112c-.367-.367-.805-.613-1.18-.965C404.438 285.332 416 248.035 416 208 416 93.313 322.695 0 208 0S0 93.313 0 208s93.305 208 208 208c40.035 0 77.332-11.563 109.098-31.242.354.375.598.813.965 1.18l112 112C439.43 507.313 451.719 512 464 512c12.281 0 24.57-4.688 33.938-14.063 18.75-18.734 18.75-49.14 0-67.874zM64 208c0-79.406 64.602-144 144-144s144 64.594 144 144-64.602 144-144 144S64 287.406 64 208z"></path>
      <path d="M272 176H144c-17.672 0-32 14.328-32 32s14.328 32 32 32h128c17.672 0 32-14.328 32-32s-14.328-32-32-32z"></path>
    </svg>
  );
}

export function ZoomIn() {
    return (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="20"
        height="20"
        fill="#000"
        version="1.1"
        viewBox="0 0 512 512"
        xmlSpace="preserve"
      >
        <path d="M497.938 430.063l-112-112c-.313-.313-.637-.607-.955-.909C404.636 285.403 416 248.006 416 208 416 93.313 322.695 0 208 0S0 93.313 0 208s93.305 208 208 208c40.007 0 77.404-11.364 109.154-31.018.302.319.596.643.909.955l112 112C439.43 507.313 451.719 512 464 512c12.281 0 24.57-4.688 33.938-14.063 18.75-18.734 18.75-49.14 0-67.874zM64 208c0-79.406 64.602-144 144-144s144 64.594 144 144-64.602 144-144 144S64 287.406 64 208z"></path>
        <path d="M272 176h-32v-32c0-17.672-14.328-32-32-32s-32 14.328-32 32v32h-32c-17.672 0-32 14.328-32 32s14.328 32 32 32h32v32c0 17.672 14.328 32 32 32s32-14.328 32-32v-32h32c17.672 0 32-14.328 32-32s-14.328-32-32-32z"></path>
      </svg>
    );
  }