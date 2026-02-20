import React from 'react'

import {
  AnimatedPipe,
  LiquidFillGaugeWrapper,
  SensorIndicator,
  TreatmentSystem,
  titleProps,
} from './detailed'

const buildMockMd = () => {
  return {
    get: (key, field) => {
      if (field === 'current_value') {
        if (key === 'feedtanklevel') return 61
        if (key === 'producttanklevel') return 78
        if (key === 'feedpumprun') return true
        if (key === 'ropumprun') return true
        return 0
      }
      if (field === 'abbreviated_name') return key?.slice(0, 3)?.toUpperCase() || ''
      if (field === 'units') return ''
      if (field === 'on_click') return () => {}
      return ''
    },
  }
}

const SimplifiedROSystem = ({ md = buildMockMd() }) => {
  return (
    <svg viewBox="0 0 720 360" width="100%" height="320" role="img" aria-label="Simplified RO system">
      <rect rx="12" x="10" y="10" width="700" height="340" fill="#f5f7fa" stroke="#d9e2ec" />
      <text x="30" y="38" {...titleProps}>
        SIMPLIFIED RO SYSTEM
      </text>

      <text x="120" y="70" fontSize="14" fontWeight="600">
        Feed Tank
      </text>
      <LiquidFillGaugeWrapper
        x="150"
        y="125"
        text=""
        textDir="down"
        fillLevel={md.get('feedtanklevel', 'current_value')}
        fillColor="#8bc34a"
      />

      <AnimatedPipe
        stroke="#8bc34a"
        paths={[[[180, 125], [430, 125]]]}
        pipeOn={md.get('feedpumprun', 'current_value')}
      />

      <text x="420" y="70" fontSize="14" fontWeight="600">
        Treatment System
      </text>
      <TreatmentSystem x="470" y="125" text="" textDir="up" />

      <AnimatedPipe
        stroke="#1c8bd3"
        paths={[[[470, 145], [470, 190], [520, 190], [150, 190], [150, 245]]]}
        pipeOn={md.get('ropumprun', 'current_value')}
      />
      <text x="250" y="185" fontSize="12" fill="#2f4f6a">
        Treated Water Stream
      </text>

      <AnimatedPipe
        stroke="#1c8bd3"
        noarr
        paths={[
          [[320, 190], [320, 240]],
          [[520, 190], [520, 240]],
        ]}
        pipeOn={md.get('ropumprun', 'current_value')}
      />

      <LiquidFillGaugeWrapper
        x="150"
        y="265"
        text=""
        textDir="down"
        fillLevel={md.get('producttanklevel', 'current_value')}
        fillColor="#1c8bd3"
      />
      <text x="110" y="305" fontSize="14" fontWeight="600">
        Product Tank
      </text>

      <SensorIndicator
        x="320"
        y="270"
        line="up"
        textDir="down"
        innerText="CTP"
        outerText="7.59 ppm"
        on_click={md.get('permeatesalinity', 'on_click')}
        smallInner
        loadIfBlank={false}
      />
      <SensorIndicator
        x="520"
        y="270"
        line="up"
        textDir="down"
        innerText="NTP"
        outerText="0.03 mg/L"
        on_click={md.get('inflownitrate', 'on_click')}
        smallInner
        loadIfBlank={false}
      />
    </svg>
  )
}

export default SimplifiedROSystem
