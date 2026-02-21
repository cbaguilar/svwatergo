export const bitTables = {
  warning1: {
    0: 'Product Tank Low',
    1: 'Feed Tank Low',
    2: 'Residual Diversion Disabled',
    3: 'Product Tank Sensor Disabled',
    4: 'Feed Tank Sensor Disabled',
    5: 'Residual Tank Sensor Disabled',
    6: 'Permeate TDS Sensor Disabled',
    7: 'Nitrate Sensor Disabled',
    8: 'Feed Pressure Sensor Disabled',
    9: 'Inlet Pressure Sensor Disabled',
    10: 'Delivery Pressure Sensor Disabled',
    11: 'Feed Pressure Low',
    12: 'Delivery Pressure Low',
    13: 'Backwash Running',
  },
  warning2: {
    0: 'Permeate TDS Sensor Error',
    1: 'Feed TDS Sensor: Error or Undefined',
    2: 'Feed Pressure Sensor Error',
    3: 'Inlet Pressure Sensor Error',
    4: 'RO Pressure Sensor Error',
    5: 'Concentrate Pressure Sensor Error',
    6: 'Permeate Pressure Sensor Error',
    7: 'Delivery Pressure Sensor Error',
    8: 'Chlorine Tank Empty',
    9: 'Product Tank Sensor Error',
    10: 'Feed Tank Sensor Error',
    11: 'Residual Tank Sensor Error',
    12: 'Nitrate Sensor Error',
    13: 'Temperature Sensor Error',
  },
  alarm: {
    0: 'EStop Pressed',
    1: 'RO Pump Feedback Error',
    2: 'Pressure Fault',
    3: 'Feed Pump Off',
    4: 'Inlet Valve Closed',
    5: 'Inlet Pressure Sensor Error',
    6: 'RO Tank Sensor Error',
    7: 'Feed Tank Sensor Error',
    8: 'Chlorine Tank Empty',
    9: 'Anti-Scalant Pump Error',
  },
}

export function decodeBitfield(word, table) {
  if (!Number.isFinite(word) || !table) return []
  const value = word >>> 0
  const decoded = []
  for (const [bitStr, label] of Object.entries(table)) {
    const bit = Number.parseInt(bitStr, 10)
    if (!Number.isInteger(bit)) continue
    if ((value & (1 << bit)) !== 0) decoded.push(label)
  }
  return decoded
}

