import React from 'react'

import {
  AnimatedPipe,
  LiquidFillGaugeWrapper,
  PumpSymbol,
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

const formatReading = (value, fractionDigits = 2) => {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return '--'
  return numericValue.toLocaleString(undefined, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  })
}

const SensorReadout = ({ x, y, tag, value, unit, label }) => (
  <g transform={`translate(${x},${y})`}>
    <line x1="0" y1="-50" x2="0" y2="-23" stroke="#000" strokeWidth="2" />
    <circle cx="0" cy="0" r="23" fill="#59b5f5" stroke="#000" strokeWidth="2" />
    <text
      x="0"
      y="2"
      textAnchor="middle"
      alignmentBaseline="middle"
      fontSize="16"
      fontWeight="600"
      fill="#000"
    >
      {tag}
    </text>
    <text
      x="0"
      y="40"
      textAnchor="middle"
      fontSize="15"
      fontWeight="600"
      fill="#000"
    >
      {value} {unit}
    </text>
    <text
      x="0"
      y="60"
      textAnchor="middle"
      fontSize="12"
      fontWeight="500"
      fill="#4a5568"
    >
      {label}
    </text>
  </g>
)

const SimplifiedROSystem = ({ md = buildMockMd() }) => {
  const getCurrent = (...keys) => {
    for (const key of keys) {
      const value = md?.get?.(key, 'current_value')
      if (value !== undefined && value !== null) return value
    }
    return 0
  }

  const roRun = Boolean(getCurrent('rorun', 'ropumprun'))
  const conductivityValue = formatReading(getCurrent('permtds'))
  const nitrateValue = formatReading(getCurrent('permnitrate'))

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
        fillLevel={getCurrent('feedtanklevel')}
        fillColor="#8bc34a"
      />

      <AnimatedPipe
        stroke="#8bc34a"
        paths={[[[180, 125], [430, 125]]]}
        pipeOn={md.get('feedpumprun', 'current_value')}
      />
      <text x="305" y="70" textAnchor="middle" fontSize="14" fontWeight="600">
        RO Pump
      </text>
      <PumpSymbol x={305} y={125} innerText="P2" flow={roRun} pumpKey="ropumprun" md={md} textDir="up" />

      <text x="525" y="125" fontSize="14" fontWeight="600" dominantBaseline="middle">
        Treatment System
      </text>
      <TreatmentSystem x="470" y="125" text="" textDir="up" />

      <AnimatedPipe stroke="#8b5a2b" paths={[[[470, 105], [470, 55]]]} pipeOn={roRun} />
      <text x="482" y="60" fontSize="12" fill="#8b5a2b" dominantBaseline="middle">
        Residual Line
      </text>

      <AnimatedPipe
        stroke="#1c8bd3"
        paths={[[[470, 145], [470, 190], [520, 190], [150, 190], [150, 245]]]}
        pipeOn={roRun}
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
        pipeOn={roRun}
      />

      <LiquidFillGaugeWrapper
        x="150"
        y="265"
        text=""
        textDir="down"
        fillLevel={getCurrent('prodtanklevel', 'producttanklevel')}
        fillColor="#1c8bd3"
      />
      <text x="110" y="336" fontSize="14" fontWeight="600">
        Product Tank
      </text>

      <SensorReadout
        x="320"
        y="270"
        tag="CTP"
        value={conductivityValue}
        unit="µS/cm"
        label="Conductivity"
      />
      <SensorReadout
        x="520"
        y="270"
        tag="NTP"
        value={nitrateValue}
        unit="mg/L as NO3-N"
        label="Nitrate (as NO3-N)"
      />
    </svg>
  )
}

export default SimplifiedROSystem
