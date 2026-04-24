import React from 'react'

function isPrimitive(v) {
  return v === null || typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean'
}

function flatten(obj, prefix = '') {
  const rows = []
  if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
    for (const key of Object.keys(obj)) {
      const path = prefix ? `${prefix}.${key}` : key
      const val = obj[key]
      if (val && typeof val === 'object' && !Array.isArray(val)) {
        rows.push(...flatten(val, path))
      } else {
        rows.push({ path, value: val })
      }
    }
  } else if (Array.isArray(obj)) {
    // treat array as single value
    rows.push({ path: prefix || '', value: obj })
  }
  return rows
}

function stringifyValue(v) {
  if (v === undefined) return ''
  if (v === null) return ''
  if (isPrimitive(v)) return String(v)
  try {
    return JSON.stringify(v)
  } catch (e) {
    return String(v)
  }
}

export default function AdvancedDiff({ versiune_veche = {}, versiune_noua = {} }) {
  // build flattened map of paths
  const oldRows = flatten(versiune_veche)
  const newRows = flatten(versiune_noua)

  const mapOld = new Map(oldRows.map(r => [r.path, r.value]))
  const mapNew = new Map(newRows.map(r => [r.path, r.value]))

  const allPaths = Array.from(new Set([...mapOld.keys(), ...mapNew.keys()])).sort()

  const rows = allPaths.map(path => {
    const oldVal = mapOld.has(path) ? mapOld.get(path) : undefined
    const newVal = mapNew.has(path) ? mapNew.get(path) : undefined
    const equal = JSON.stringify(oldVal) === JSON.stringify(newVal)

    let leftStyle = {}
    let rightStyle = {}

    if (!equal) {
      // if only new exists => added field (green on right, red on left)
      if (oldVal === undefined && newVal !== undefined) {
        leftStyle = { background: '#ffdddd' }
        rightStyle = { background: '#ddffdd' }
      } else if (oldVal !== undefined && newVal === undefined) {
        // removed in new => red on left, green on right (to indicate missing/new fill)
        leftStyle = { background: '#ffdddd' }
        rightStyle = { background: '#ddffdd' }
      } else {
        // modified: highlight old (red) and new (green)
        leftStyle = { background: '#ffdddd' }
        rightStyle = { background: '#ddffdd' }
      }
    }

    return {
      path,
      oldVal,
      newVal,
      leftStyle,
      rightStyle,
      equal
    }
  })

  return (
    <div style={{ fontFamily: 'Segoe UI, Arial, sans-serif', margin: 12 }}>
      <h3>Advanced Side-by-Side Diff</h3>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left', padding: 8, width: '30%' }}>Field</th>
            <th style={{ textAlign: 'left', padding: 8, width: '35%' }}>Versiune veche</th>
            <th style={{ textAlign: 'left', padding: 8, width: '35%' }}>Versiune noua</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.path} style={{ borderBottom: '1px solid #eee' }}>
              <td style={{ padding: 8, verticalAlign: 'top' }}>{r.path}</td>
              <td style={{ padding: 8, verticalAlign: 'top', ...r.leftStyle }}>{stringifyValue(r.oldVal)}</td>
              <td style={{ padding: 8, verticalAlign: 'top', ...r.rightStyle }}>{stringifyValue(r.newVal)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
