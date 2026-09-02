import React, { useEffect, useMemo, useRef, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import {
  CAlert,
  CBadge,
  CButton,
  CButtonGroup,
  CCard,
  CCardBody,
  CCardHeader,
  CCol,
  CFormCheck,
  CFormInput,
  CFormLabel,
  CFormSelect,
  CProgress,
  CProgressBar,
  CRow,
  CSpinner,
  CTable,
  CTableBody,
  CTableDataCell,
  CTableHead,
  CTableHeaderCell,
  CTableRow,
} from '@coreui/react'
import {
  audioArtifactPlaybackUrl,
  createAudioInferenceRun,
  fetchAnalyticsJob,
  fetchAudioArtifacts,
  fetchAudioSources,
  localAudioPlaybackUrl,
  localAudioSpectrogramUrl,
  stageAudioFile,
} from '../../api/audioInference'

const SITE_OPTIONS = [
  { value: 'bluerock', label: 'Bluerock' },
  { value: 'pryorfarm', label: 'Pryor Farms' },
  { value: 'santateresa', label: 'Santa Teresa' },
]

const DEFAULT_MODEL_PATH =
  'data/checkpoints/ropumprun_on_pca_svm_Pryor_Farms_1_2026-02-25_10s/audio_pca_svm_model.joblib'

const DEFAULT_LOCAL_AUDIO_PATH =
  'data/raw/camera_5_2026-03-01_wav/camera=camera_5/date=2026-03-01/camera_5_2026-03-01T22-03-09.582000Z_chunk=000000.wav'

const POLL_MS = 1200
const MEL_BANDS = 64

function hzToMel(hz) {
  return 2595 * Math.log10(1 + hz / 700)
}

function melToHz(mel) {
  return 700 * (10 ** (mel / 2595) - 1)
}

function melFrequencies(sampleRate, bands = MEL_BANDS) {
  const minMel = hzToMel(30)
  const maxMel = hzToMel(Math.min(sampleRate / 2, 8000))
  return Array.from({ length: bands }, (_, index) => {
    const t = bands <= 1 ? 0 : index / (bands - 1)
    return melToHz(minMel + t * (maxMel - minMel))
  })
}

function goertzelPower(samples, start, frameSize, frequency, sampleRate) {
  const omega = (2 * Math.PI * frequency) / sampleRate
  const coeff = 2 * Math.cos(omega)
  let q0 = 0
  let q1 = 0
  let q2 = 0
  for (let i = 0; i < frameSize; i += 1) {
    const sample = samples[start + i] || 0
    const windowValue = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / Math.max(1, frameSize - 1))
    q0 = coeff * q1 - q2 + sample * windowValue
    q2 = q1
    q1 = q0
  }
  return Math.max(1e-12, q1 * q1 + q2 * q2 - coeff * q1 * q2)
}

function computeMelSpectrogram(audioBuffer) {
  const sampleRate = audioBuffer.sampleRate
  const samples = audioBuffer.getChannelData(0)
  const frameSize = Math.min(2048, 2 ** Math.floor(Math.log2(Math.max(256, sampleRate * 0.046))))
  const hopSize = Math.max(128, Math.floor(frameSize / 2))
  const rawFrameCount = Math.max(1, Math.floor((samples.length - frameSize) / hopSize) + 1)
  const maxFrames = 420
  const frameStride = Math.max(1, Math.ceil(rawFrameCount / maxFrames))
  const frameCount = Math.ceil(rawFrameCount / frameStride)
  const frequencies = melFrequencies(sampleRate)
  const matrix = Array.from({ length: MEL_BANDS }, () => new Array(frameCount).fill(0))
  let min = Infinity
  let max = -Infinity

  for (let frame = 0; frame < frameCount; frame += 1) {
    const start = Math.min(samples.length - frameSize, frame * frameStride * hopSize)
    for (let band = 0; band < frequencies.length; band += 1) {
      const value =
        10 * Math.log10(goertzelPower(samples, start, frameSize, frequencies[band], sampleRate))
      matrix[MEL_BANDS - band - 1][frame] = value
      min = Math.min(min, value)
      max = Math.max(max, value)
    }
  }

  return {
    matrix,
    min,
    max,
    sampleRate,
    durationSeconds: audioBuffer.duration,
  }
}

function spectrogramColor(t) {
  const stops = [
    [15, 23, 42],
    [30, 64, 175],
    [6, 182, 212],
    [163, 230, 53],
    [250, 204, 21],
  ]
  const scaled = Math.max(0, Math.min(1, t)) * (stops.length - 1)
  const index = Math.min(stops.length - 2, Math.floor(scaled))
  const local = scaled - index
  return stops[index].map((start, channel) =>
    Math.round(start + (stops[index + 1][channel] - start) * local),
  )
}

function drawMelSpectrogram(canvas, spectrogram) {
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const rows = spectrogram.matrix.length
  const cols = spectrogram.matrix[0]?.length || 0
  const dpr = window.devicePixelRatio || 1
  const width = Math.max(320, canvas.clientWidth)
  const height = Math.max(180, canvas.clientHeight)
  canvas.width = Math.floor(width * dpr)
  canvas.height = Math.floor(height * dpr)
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, width, height)
  ctx.fillStyle = '#0f172a'
  ctx.fillRect(0, 0, width, height)
  if (!rows || !cols) return

  const range = Math.max(1e-6, spectrogram.max - spectrogram.min)
  const cellWidth = width / cols
  const cellHeight = height / rows
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      const normalized = (spectrogram.matrix[row][col] - spectrogram.min) / range
      const [r, g, b] = spectrogramColor(normalized)
      ctx.fillStyle = `rgb(${r}, ${g}, ${b})`
      ctx.fillRect(col * cellWidth, row * cellHeight, Math.ceil(cellWidth), Math.ceil(cellHeight))
    }
  }
}

function toLocalDateTimeInputValue(date) {
  const d = new Date(date)
  if (Number.isNaN(d.getTime())) return ''
  const offsetMs = d.getTimezoneOffset() * 60 * 1000
  return new Date(d.getTime() - offsetMs).toISOString().slice(0, 16)
}

function fromLocalDateTimeInputValue(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return d.toISOString()
}

function defaultRange() {
  const end = new Date()
  const start = new Date(end.getTime() - 24 * 60 * 60 * 1000)
  return {
    start: toLocalDateTimeInputValue(start),
    end: toLocalDateTimeInputValue(end),
  }
}

function hashSearchParams() {
  if (typeof window === 'undefined') return new URLSearchParams()
  const hash = window.location.hash || ''
  const queryIndex = hash.indexOf('?')
  if (queryIndex < 0) return new URLSearchParams()
  return new URLSearchParams(hash.slice(queryIndex + 1))
}

function paramOr(params, key, fallback) {
  const value = params.get(key)
  return value == null || value === '' ? fallback : value
}

function boolParam(params, key, fallback = false) {
  const value = String(params.get(key) || '')
    .trim()
    .toLowerCase()
  if (!value) return fallback
  return ['1', 'true', 'yes', 'on'].includes(value)
}

function initialConfig(rangeDefaults) {
  const params = hashSearchParams()
  return {
    site: paramOr(params, 'site', 'bluerock'),
    sourceKey: paramOr(params, 'source', ''),
    mode: paramOr(params, 'mode', 'upload'),
    localPath: paramOr(params, 'localPath', DEFAULT_LOCAL_AUDIO_PATH),
    artifactID: paramOr(params, 'artifactId', ''),
    start: paramOr(params, 'start', rangeDefaults.start),
    end: paramOr(params, 'end', rangeDefaults.end),
    modelPath: paramOr(params, 'modelPath', DEFAULT_MODEL_PATH),
    modelKind: paramOr(params, 'modelKind', 'pca_svm'),
    modelId: paramOr(params, 'modelId', ''),
    modelVersion: paramOr(params, 'modelVersion', ''),
    autoRun: boolParam(params, 'run', false),
  }
}

function formatDateTime(value) {
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value || ''
  return d.toLocaleString()
}

function formatNumber(value, digits = 4) {
  const n = Number(value)
  if (!Number.isFinite(n)) return ''
  return n.toFixed(digits)
}

function artifactLabel(item) {
  if (!item) return ''
  const source = item.display_name || item.source_key || 'audio'
  const when = formatDateTime(item.start_time)
  const format = item.format ? `.${item.format}` : ''
  return `${source}${format} - ${when}`
}

function artifactS3URI(item) {
  if (!item?.s3_bucket || !item?.s3_key) return ''
  return `s3://${item.s3_bucket}/${item.s3_key}`
}

function extractPayload(job) {
  const result = job?.result || {}
  const servicePayload = result?.inference_response?.payload
  if (servicePayload?.results) return servicePayload
  const workerResult = result?.worker_result
  if (workerResult?.results) return workerResult
  if (result?.results) return result
  return null
}

function firstInferenceResult(job) {
  const payload = extractPayload(job)
  const rows = Array.isArray(payload?.results) ? payload.results : []
  return rows[0] || null
}

function resultPredictions(row) {
  return row?.predictions && typeof row.predictions === 'object' ? row.predictions : null
}

function projectionVector(row) {
  const pred = resultPredictions(row)
  if (Array.isArray(pred?.pca_projection)) return pred.pca_projection.map(Number)
  if (Array.isArray(row?.embedding?.vector)) return row.embedding.vector.map(Number)
  return []
}

function probabilityRows(predictions) {
  if (!Array.isArray(predictions?.probabilities)) return []
  return predictions.probabilities.map((value, index) => ({
    label:
      index === 1 && predictions.positive_label
        ? String(predictions.positive_label)
        : `class ${index}`,
    value: Number(value),
  }))
}

function buildRunPayload({ site, modelPath, modelKind, modelId, modelVersion, input }) {
  const model = {
    model_kind: modelKind,
  }
  if (modelId.trim()) model.model_id = modelId.trim()
  if (modelVersion.trim()) model.version = modelVersion.trim()
  if (modelPath.trim()) model.model_path = modelPath.trim()

  return {
    site,
    model,
    outputs: {
      predictions: true,
      embeddings: true,
      metadata: true,
    },
    batch: {
      mode: 'async',
      max_items: 1,
    },
    inputs: [input],
  }
}

function updateHashQuery(values) {
  if (typeof window === 'undefined') return ''
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(values)) {
    if (value != null && String(value).trim() !== '') {
      params.set(key, String(value))
    }
  }
  const next = `#/audio-inference?${params.toString()}`
  window.history.replaceState(null, '', next)
  return `${window.location.origin}${window.location.pathname}${next}`
}

function projectionChartOption(vector) {
  const x = Number(vector[0])
  const y = Number(vector[1])
  const hasPoint = Number.isFinite(x) && Number.isFinite(y)
  const pad = Math.max(1, Math.abs(x || 0), Math.abs(y || 0)) * 0.3
  const minX = hasPoint ? x - pad : -1
  const maxX = hasPoint ? x + pad : 1
  const minY = hasPoint ? y - pad : -1
  const maxY = hasPoint ? y + pad : 1

  return {
    animation: false,
    grid: { left: 48, right: 18, top: 18, bottom: 42 },
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        const value = params?.value || []
        return `PC1 ${formatNumber(value[0])}<br/>PC2 ${formatNumber(value[1])}`
      },
    },
    xAxis: {
      name: 'PC1',
      min: minX,
      max: maxX,
      splitLine: { lineStyle: { color: '#e5e7eb' } },
      axisLine: { lineStyle: { color: '#94a3b8' } },
    },
    yAxis: {
      name: 'PC2',
      min: minY,
      max: maxY,
      splitLine: { lineStyle: { color: '#e5e7eb' } },
      axisLine: { lineStyle: { color: '#94a3b8' } },
    },
    series: [
      {
        name: 'Audio window',
        type: 'scatter',
        symbolSize: 18,
        data: hasPoint ? [[x, y]] : [],
        itemStyle: {
          color: '#2563eb',
          borderColor: '#0f172a',
          borderWidth: 2,
        },
      },
    ],
  }
}

const AudioInferenceExplorer = () => {
  const rangeDefaults = useMemo(() => defaultRange(), [])
  const urlConfig = useMemo(() => initialConfig(rangeDefaults), [rangeDefaults])
  const [site, setSite] = useState(urlConfig.site)
  const [sourceKey, setSourceKey] = useState(urlConfig.sourceKey)
  const [mode, setMode] = useState(urlConfig.mode)
  const [file, setFile] = useState(null)
  const [fileUrl, setFileUrl] = useState('')
  const [localPath, setLocalPath] = useState(urlConfig.localPath)
  const [sources, setSources] = useState([])
  const [artifacts, setArtifacts] = useState([])
  const [selectedArtifactID, setSelectedArtifactID] = useState(urlConfig.artifactID)
  const [start, setStart] = useState(urlConfig.start)
  const [end, setEnd] = useState(urlConfig.end)
  const [modelPath, setModelPath] = useState(urlConfig.modelPath)
  const [modelKind, setModelKind] = useState(urlConfig.modelKind)
  const [modelId, setModelId] = useState(urlConfig.modelId)
  const [modelVersion, setModelVersion] = useState(urlConfig.modelVersion)
  const [autoPoll, setAutoPoll] = useState(true)
  const [loadingSources, setLoadingSources] = useState(false)
  const [loadingArtifacts, setLoadingArtifacts] = useState(false)
  const [running, setRunning] = useState(false)
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [shareStatus, setShareStatus] = useState('')
  const [spectrogram, setSpectrogram] = useState(null)
  const [spectrogramStatus, setSpectrogramStatus] = useState('')
  const [spectrogramError, setSpectrogramError] = useState('')
  const autoRunRef = useRef(urlConfig.autoRun)
  const pollTimerRef = useRef(null)
  const spectrogramCanvasRef = useRef(null)

  const selectedArtifact = useMemo(
    () => artifacts.find((item) => String(item.id) === String(selectedArtifactID)) || null,
    [artifacts, selectedArtifactID],
  )
  const inferenceRow = firstInferenceResult(job)
  const predictions = resultPredictions(inferenceRow)
  const projection = projectionVector(inferenceRow)
  const probabilities = probabilityRows(predictions)
  const audioUrl =
    mode === 'upload'
      ? fileUrl
      : mode === 'local_path'
        ? localAudioPlaybackUrl(localPath)
        : selectedArtifact?.public_url || audioArtifactPlaybackUrl(selectedArtifactID)
  const serverSpectrogramUrl = mode === 'local_path' ? localAudioSpectrogramUrl(localPath) : ''
  const payload = extractPayload(job)

  useEffect(() => {
    const controller = new AbortController()
    setLoadingSources(true)
    fetchAudioSources({ site, signal: controller.signal })
      .then((data) => {
        const next = Array.isArray(data?.sources) ? data.sources : []
        setSources(next)
        setSourceKey((current) => {
          if (current && next.some((item) => item.source_key === current)) return current
          return next[0]?.source_key || ''
        })
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setSources([])
      })
      .finally(() => setLoadingSources(false))
    return () => controller.abort()
  }, [site])

  useEffect(() => {
    if (mode !== 'database') return undefined
    const controller = new AbortController()
    setLoadingArtifacts(true)
    fetchAudioArtifacts({
      site,
      sourceKey,
      start: fromLocalDateTimeInputValue(start),
      end: fromLocalDateTimeInputValue(end),
      limit: 50,
      signal: controller.signal,
    })
      .then((data) => {
        const next = Array.isArray(data?.artifacts) ? data.artifacts : []
        setArtifacts(next)
        setSelectedArtifactID((current) => {
          if (current && next.some((item) => String(item.id) === String(current))) return current
          if (
            urlConfig.artifactID &&
            next.some((item) => String(item.id) === String(urlConfig.artifactID))
          ) {
            return String(urlConfig.artifactID)
          }
          return next[0]?.id ? String(next[0].id) : ''
        })
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setArtifacts([])
      })
      .finally(() => setLoadingArtifacts(false))
    return () => controller.abort()
  }, [mode, site, sourceKey, start, end, urlConfig.artifactID])

  useEffect(() => {
    if (!file) {
      setFileUrl('')
      return undefined
    }
    const url = URL.createObjectURL(file)
    setFileUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  useEffect(() => {
    if (!autoPoll || !job?.id || !['queued', 'running'].includes(job.status)) return undefined
    pollTimerRef.current = window.setTimeout(() => {
      fetchAnalyticsJob(job.id)
        .then((data) => setJob(data?.job || null))
        .catch((err) => setError(err.message || 'Failed to poll inference job'))
    }, POLL_MS)
    return () => {
      if (pollTimerRef.current) window.clearTimeout(pollTimerRef.current)
    }
  }, [autoPoll, job])

  useEffect(() => {
    if (!autoRunRef.current || running || job) return
    if (mode === 'database' && !selectedArtifact) return
    if (mode === 'upload') return
    autoRunRef.current = false
    runInference()
  }, [job, mode, running, selectedArtifact]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!audioUrl || serverSpectrogramUrl) {
      setSpectrogram(null)
      setSpectrogramStatus('')
      setSpectrogramError('')
      return undefined
    }
    let cancelled = false
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext
    if (!AudioContextCtor) {
      setSpectrogramError('This browser does not expose Web Audio decoding.')
      return undefined
    }
    const audioContext = new AudioContextCtor()
    setSpectrogram(null)
    setSpectrogramStatus('Computing mel spectrogram...')
    setSpectrogramError('')

    fetch(audioUrl)
      .then((response) => {
        if (!response.ok) throw new Error(`Audio fetch failed with status ${response.status}`)
        return response.arrayBuffer()
      })
      .then((buffer) => audioContext.decodeAudioData(buffer))
      .then((decoded) => {
        if (cancelled) return
        const next = computeMelSpectrogram(decoded)
        setSpectrogram(next)
        setSpectrogramStatus('')
      })
      .catch((err) => {
        if (!cancelled) {
          setSpectrogram(null)
          setSpectrogramStatus('')
          setSpectrogramError(err.message || 'Unable to compute mel spectrogram.')
        }
      })
      .finally(() => {
        audioContext.close().catch(() => {})
      })

    return () => {
      cancelled = true
      audioContext.close().catch(() => {})
    }
  }, [audioUrl, serverSpectrogramUrl])

  useEffect(() => {
    if (!spectrogram || !spectrogramCanvasRef.current) return
    drawMelSpectrogram(spectrogramCanvasRef.current, spectrogram)
  }, [spectrogram])

  async function refreshJob() {
    if (!job?.id) return
    setError('')
    const data = await fetchAnalyticsJob(job.id)
    setJob(data?.job || null)
  }

  async function runInference() {
    setError('')
    setRunning(true)
    setJob(null)
    try {
      let input
      if (mode === 'upload') {
        if (!file) throw new Error('Choose an audio file to upload.')
        const staged = await stageAudioFile(file)
        input = {
          input_id: file.name || 'upload',
          type: 'upload',
          staged_ref: staged.staged_ref,
        }
      } else if (mode === 'database') {
        if (!selectedArtifact) throw new Error('Choose an audio artifact.')
        const uri = artifactS3URI(selectedArtifact)
        if (!uri) throw new Error('Selected artifact is missing s3_bucket or s3_key.')
        input = {
          input_id: `audio_artifact_${selectedArtifact.id}`,
          type: 's3_uri',
          uri,
        }
      } else {
        if (!localPath.trim()) throw new Error('Enter a server-local audio path.')
        input = {
          input_id: localPath.split('/').pop() || 'local_audio',
          type: 'local_path',
          path: localPath.trim(),
        }
      }
      const request = buildRunPayload({
        site,
        modelPath,
        modelKind,
        modelId,
        modelVersion,
        input,
      })
      const created = await createAudioInferenceRun(request)
      setJob(created?.job || null)
    } catch (err) {
      setError(err.message || 'Audio inference failed')
    } finally {
      setRunning(false)
    }
  }

  async function copyPrefilledLink({ run = false } = {}) {
    setShareStatus('')
    const url = updateHashQuery({
      apiBackend: 'tailscale',
      site,
      source: sourceKey,
      mode,
      localPath: mode === 'local_path' ? localPath : '',
      artifactId: mode === 'database' ? selectedArtifactID : '',
      start: mode === 'database' ? start : '',
      end: mode === 'database' ? end : '',
      modelPath,
      modelKind,
      modelId,
      modelVersion,
      run: run ? '1' : '',
    })
    try {
      await navigator.clipboard.writeText(url)
      setShareStatus(run ? 'Ready-to-run link copied.' : 'Prefilled link copied.')
    } catch {
      setShareStatus(url)
    }
  }

  const statusColor =
    job?.status === 'succeeded'
      ? 'success'
      : job?.status === 'failed'
        ? 'danger'
        : job?.status === 'running'
          ? 'info'
          : 'secondary'

  return (
    <>
      <CRow>
        <CCol xs={12}>
          <CCard className="mb-4">
            <CCardHeader className="d-flex align-items-center justify-content-between gap-3">
              <strong>Audio Inference Explorer</strong>
              {job?.status && <CBadge color={statusColor}>{job.status}</CBadge>}
            </CCardHeader>
            <CCardBody>
              {error && (
                <CAlert color="danger" className="mb-4">
                  {error}
                </CAlert>
              )}
              <CRow className="g-3">
                <CCol md={3}>
                  <CFormLabel htmlFor="audio-site">Site</CFormLabel>
                  <CFormSelect
                    id="audio-site"
                    value={site}
                    onChange={(event) => setSite(event.target.value)}
                  >
                    {SITE_OPTIONS.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </CFormSelect>
                </CCol>
                <CCol md={3}>
                  <CFormLabel htmlFor="audio-source">Source</CFormLabel>
                  <CFormSelect
                    id="audio-source"
                    value={sourceKey}
                    disabled={loadingSources || sources.length === 0}
                    onChange={(event) => setSourceKey(event.target.value)}
                  >
                    {sources.length === 0 && <option value="">No sources</option>}
                    {sources.map((item) => (
                      <option key={item.source_key} value={item.source_key}>
                        {item.display_name || item.source_key}
                      </option>
                    ))}
                  </CFormSelect>
                </CCol>
                <CCol md={3}>
                  <CFormLabel>Input</CFormLabel>
                  <CButtonGroup className="d-flex">
                    <CButton
                      color={mode === 'upload' ? 'primary' : 'secondary'}
                      variant={mode === 'upload' ? undefined : 'outline'}
                      onClick={() => setMode('upload')}
                    >
                      Upload
                    </CButton>
                    <CButton
                      color={mode === 'local_path' ? 'primary' : 'secondary'}
                      variant={mode === 'local_path' ? undefined : 'outline'}
                      onClick={() => setMode('local_path')}
                    >
                      Path
                    </CButton>
                    <CButton
                      color={mode === 'database' ? 'primary' : 'secondary'}
                      variant={mode === 'database' ? undefined : 'outline'}
                      onClick={() => setMode('database')}
                    >
                      Database
                    </CButton>
                  </CButtonGroup>
                </CCol>
                <CCol md={3}>
                  <CFormLabel htmlFor="model-kind">Model Kind</CFormLabel>
                  <CFormSelect
                    id="model-kind"
                    value={modelKind}
                    onChange={(event) => setModelKind(event.target.value)}
                  >
                    <option value="pca_svm">PCA/SVM</option>
                    <option value="tiny_cnn">Tiny CNN</option>
                    <option value="auto">Auto</option>
                  </CFormSelect>
                </CCol>

                {mode === 'upload' && (
                  <CCol md={6}>
                    <CFormLabel htmlFor="audio-file">Audio File</CFormLabel>
                    <CFormInput
                      id="audio-file"
                      type="file"
                      accept="audio/*,.wav,.webm,.mp3,.m4a"
                      onChange={(event) => setFile(event.target.files?.[0] || null)}
                    />
                  </CCol>
                )}

                {mode === 'local_path' && (
                  <CCol md={6}>
                    <CFormLabel htmlFor="audio-local-path">Server Audio Path</CFormLabel>
                    <CFormInput
                      id="audio-local-path"
                      value={localPath}
                      onChange={(event) => setLocalPath(event.target.value)}
                    />
                  </CCol>
                )}

                {mode === 'database' && (
                  <>
                    <CCol md={3}>
                      <CFormLabel htmlFor="audio-start">Start</CFormLabel>
                      <CFormInput
                        id="audio-start"
                        type="datetime-local"
                        value={start}
                        onChange={(event) => setStart(event.target.value)}
                      />
                    </CCol>
                    <CCol md={3}>
                      <CFormLabel htmlFor="audio-end">End</CFormLabel>
                      <CFormInput
                        id="audio-end"
                        type="datetime-local"
                        value={end}
                        onChange={(event) => setEnd(event.target.value)}
                      />
                    </CCol>
                    <CCol md={6}>
                      <CFormLabel htmlFor="audio-artifact">Audio Artifact</CFormLabel>
                      <CFormSelect
                        id="audio-artifact"
                        value={selectedArtifactID}
                        disabled={loadingArtifacts || artifacts.length === 0}
                        onChange={(event) => setSelectedArtifactID(event.target.value)}
                      >
                        {artifacts.length === 0 && <option value="">No artifacts</option>}
                        {artifacts.map((item) => (
                          <option key={item.id} value={item.id}>
                            {artifactLabel(item)}
                          </option>
                        ))}
                      </CFormSelect>
                    </CCol>
                  </>
                )}

                <CCol md={6}>
                  <CFormLabel htmlFor="model-path">Model Path</CFormLabel>
                  <CFormInput
                    id="model-path"
                    value={modelPath}
                    onChange={(event) => setModelPath(event.target.value)}
                  />
                </CCol>
                <CCol md={3}>
                  <CFormLabel htmlFor="model-id">Model ID</CFormLabel>
                  <CFormInput
                    id="model-id"
                    value={modelId}
                    placeholder="optional"
                    onChange={(event) => setModelId(event.target.value)}
                  />
                </CCol>
                <CCol md={3}>
                  <CFormLabel htmlFor="model-version">Version</CFormLabel>
                  <CFormInput
                    id="model-version"
                    value={modelVersion}
                    placeholder="optional"
                    onChange={(event) => setModelVersion(event.target.value)}
                  />
                </CCol>
                <CCol xs={12} className="d-flex align-items-center gap-3">
                  <CButton color="primary" disabled={running} onClick={runInference}>
                    {running && <CSpinner size="sm" className="me-2" />}
                    Run Inference
                  </CButton>
                  <CButton
                    color="secondary"
                    variant="outline"
                    disabled={!job?.id}
                    onClick={refreshJob}
                  >
                    Refresh
                  </CButton>
                  <CFormCheck
                    id="auto-poll"
                    checked={autoPoll}
                    onChange={(event) => setAutoPoll(event.target.checked)}
                    label="Auto poll"
                  />
                  <CButton color="secondary" variant="outline" onClick={() => copyPrefilledLink()}>
                    Copy Link
                  </CButton>
                  <CButton
                    color="secondary"
                    variant="outline"
                    onClick={() => copyPrefilledLink({ run: true })}
                  >
                    Copy Ready Link
                  </CButton>
                </CCol>
                {shareStatus && (
                  <CCol xs={12}>
                    <CAlert color="info" className="mb-0 text-break">
                      {shareStatus}
                    </CAlert>
                  </CCol>
                )}
              </CRow>
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>

      <CRow>
        <CCol lg={5}>
          <CCard className="mb-4">
            <CCardHeader>
              <strong>Inference Output</strong>
            </CCardHeader>
            <CCardBody>
              {audioUrl && (
                <audio className="w-100 mb-3" controls src={audioUrl}>
                  <track kind="captions" />
                </audio>
              )}

              {!inferenceRow && (
                <div className="text-body-secondary">Run inference to inspect model output.</div>
              )}

              {inferenceRow && (
                <>
                  <div className="d-flex flex-wrap gap-2 mb-3">
                    <CBadge color={inferenceRow.status === 'ok' ? 'success' : 'danger'}>
                      {inferenceRow.status}
                    </CBadge>
                    <CBadge color="secondary">{inferenceRow.model_kind}</CBadge>
                    {inferenceRow.timing_ms != null && (
                      <CBadge color="info">{inferenceRow.timing_ms} ms</CBadge>
                    )}
                  </div>

                  {inferenceRow.error && <CAlert color="danger">{inferenceRow.error}</CAlert>}

                  {predictions && (
                    <>
                      <CTable small responsive>
                        <CTableBody>
                          <CTableRow>
                            <CTableHeaderCell scope="row">Label</CTableHeaderCell>
                            <CTableDataCell>
                              {predictions.predicted_label || predictions.predicted_index}
                            </CTableDataCell>
                          </CTableRow>
                          <CTableRow>
                            <CTableHeaderCell scope="row">Task</CTableHeaderCell>
                            <CTableDataCell>{predictions.task || ''}</CTableDataCell>
                          </CTableRow>
                          {'score_positive' in predictions && (
                            <CTableRow>
                              <CTableHeaderCell scope="row">Positive Score</CTableHeaderCell>
                              <CTableDataCell>
                                {formatNumber(predictions.score_positive)}
                              </CTableDataCell>
                            </CTableRow>
                          )}
                          {predictions.mel_shape_used && (
                            <CTableRow>
                              <CTableHeaderCell scope="row">Mel Shape</CTableHeaderCell>
                              <CTableDataCell>
                                {predictions.mel_shape_used.join(' x ')}
                              </CTableDataCell>
                            </CTableRow>
                          )}
                        </CTableBody>
                      </CTable>

                      {probabilities.length > 0 && (
                        <div className="mb-3">
                          <div className="fw-semibold mb-2">Probabilities</div>
                          {probabilities.map((item) => (
                            <div key={item.label} className="mb-2">
                              <div className="d-flex justify-content-between small mb-1">
                                <span>{item.label}</span>
                                <span>{formatNumber(item.value, 3)}</span>
                              </div>
                              <CProgress thin>
                                <CProgressBar
                                  value={Math.max(0, Math.min(100, item.value * 100))}
                                />
                              </CProgress>
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </>
              )}
            </CCardBody>
          </CCard>

          <CCard className="mb-4">
            <CCardHeader>
              <strong>Mel Spectrogram</strong>
            </CCardHeader>
            <CCardBody>
              {spectrogramStatus && (
                <div className="d-flex align-items-center gap-2 text-body-secondary mb-3">
                  <CSpinner size="sm" />
                  <span>{spectrogramStatus}</span>
                </div>
              )}
              {spectrogramError && (
                <CAlert color="warning" className="mb-3">
                  {spectrogramError}
                </CAlert>
              )}
              {serverSpectrogramUrl ? (
                <img
                  alt="Mel spectrogram"
                  className="w-100 rounded"
                  src={serverSpectrogramUrl}
                  style={{ minHeight: 220, background: '#0f172a', objectFit: 'fill' }}
                />
              ) : (
                <canvas
                  ref={spectrogramCanvasRef}
                  className="w-100 rounded"
                  style={{ height: 220, background: '#0f172a' }}
                />
              )}
              {serverSpectrogramUrl ? (
                <div className="d-flex flex-wrap gap-2 mt-3">
                  <CBadge color="secondary">{MEL_BANDS} mel bands</CBadge>
                  <CBadge color="secondary">server rendered</CBadge>
                </div>
              ) : spectrogram ? (
                <div className="d-flex flex-wrap gap-2 mt-3">
                  <CBadge color="secondary">{MEL_BANDS} mel bands</CBadge>
                  <CBadge color="secondary">
                    {formatNumber(spectrogram.durationSeconds, 2)} s
                  </CBadge>
                  <CBadge color="secondary">{spectrogram.sampleRate} Hz</CBadge>
                </div>
              ) : (
                !spectrogramStatus &&
                !spectrogramError && (
                  <div className="text-body-secondary mt-3">
                    Select audio to render its mel view.
                  </div>
                )
              )}
            </CCardBody>
          </CCard>
        </CCol>

        <CCol lg={7}>
          <CCard className="mb-4">
            <CCardHeader>
              <strong>Embedding Projection</strong>
            </CCardHeader>
            <CCardBody>
              {projection.length >= 2 ? (
                <>
                  <ReactECharts
                    option={projectionChartOption(projection)}
                    style={{ height: 360, width: '100%' }}
                    notMerge
                  />
                  <CTable small responsive className="mt-3">
                    <CTableHead>
                      <CTableRow>
                        <CTableHeaderCell>Dimension</CTableHeaderCell>
                        <CTableHeaderCell>Value</CTableHeaderCell>
                      </CTableRow>
                    </CTableHead>
                    <CTableBody>
                      {projection.slice(0, 8).map((value, index) => (
                        <CTableRow key={index}>
                          <CTableDataCell>PC{index + 1}</CTableDataCell>
                          <CTableDataCell>{formatNumber(value)}</CTableDataCell>
                        </CTableRow>
                      ))}
                    </CTableBody>
                  </CTable>
                </>
              ) : (
                <div className="text-body-secondary">
                  This model response does not include a low-dimensional projection.
                </div>
              )}
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>

      {payload?.summary && (
        <CRow>
          <CCol xs={12}>
            <CCard>
              <CCardHeader>
                <strong>Run Summary</strong>
              </CCardHeader>
              <CCardBody>
                <pre className="mb-0 small text-wrap">
                  {JSON.stringify(payload.summary, null, 2)}
                </pre>
              </CCardBody>
            </CCard>
          </CCol>
        </CRow>
      )}
    </>
  )
}

export default AudioInferenceExplorer
