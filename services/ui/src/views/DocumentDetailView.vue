<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import client from '../api/client.js'
import {
  formatDateTime,
  formatDocType,
  formatAmount,
  formatBytes,
  statusLabel,
  statusColor,
  statusIcon,
  dateRoleLabel,
  amountRoleLabel,
  SUBSTAGE_META,
} from '../utils/format.js'

const props = defineProps({ id: String })
const router = useRouter()

const doc = ref(null)
const audit = ref([])
const loading = ref(false)
const deleting = ref(false)
const downloading = ref(false)
const confirmDelete = ref(false)
const tab = ref('audit')

const previewOpen = ref(false)
const previewUrl = ref('')
const previewLoading = ref(false)
const previewLoaded = ref(false)
const previewFullscreen = ref(false)

function extOf(name) {
  const dot = (name || '').lastIndexOf('.')
  return dot > 0 ? name.slice(dot + 1).toUpperCase() : 'файл'
}

const isPdf = computed(() => doc.value?.mime_type === 'application/pdf')
const isImage = computed(() => doc.value?.mime_type?.startsWith('image/'))
const previewKind = computed(() => {
  if (!doc.value) return null
  if (isPdf.value) return 'pdf'
  if (isImage.value) return 'image'
  if (doc.value.text_content) return 'text'
  return null
})

function formatVatRate(value) {
  if (value === null || value === undefined || value === '') return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)
  const trimmed = n % 1 === 0 ? String(n) : n.toFixed(2).replace(/\.?0+$/, '')
  return `${trimmed} %`
}

const infoRows = computed(() => {
  if (!doc.value) return []
  const d = doc.value
  return [
    { label: 'Тип', value: formatDocType(d.doc_type), errorKey: 'document' },
    { label: 'Номер', value: d.number || '—', errorKey: 'number' },
    { label: 'Дата документа', value: d.doc_date || '—', errorKey: 'date' },
    { label: 'Итоговая сумма', value: d.amount_total ? formatAmount(d.amount_total, d.currency) : '—', errorKey: 'amount_total' },
    { label: 'Ставка НДС', value: formatVatRate(d.vat_rate), errorKey: 'vat_rate' },
  ]
})

const ISSUE_TEXTS = {
  unknown_document_type: 'Не удалось определить тип документа',
  checksum_failed: 'ИНН не прошёл проверку контрольной суммы',
  format_invalid: 'Некорректный формат значения',
  out_of_range_or_format: 'Дата вне допустимого диапазона',
  non_positive_or_format: 'Сумма должна быть положительной',
  hallucinated: 'Значение отсутствует в тексте документа',
}

const FIELD_LABELS = {
  document: 'Тип документа',
  doc_type: 'Тип документа',
  inn: 'ИНН',
  kpp: 'КПП',
  date: 'Дата',
  doc_date: 'Дата документа',
  amount: 'Сумма',
  amount_total: 'Итоговая сумма',
  number: 'Номер',
  doc_number: 'Номер',
  counterparty_name: 'Контрагент',
  counterparty_inn: 'ИНН контрагента',
  counterparty_kpp: 'КПП контрагента',
  vat_rate: 'Ставка НДС',
}

const CP_FIELD_LABELS = {
  name: 'название',
  inn: 'ИНН',
  kpp: 'КПП',
  form: 'форма',
  role: 'роль',
  primary: 'признак «основной»',
  added: 'добавлен',
  removed: 'удалён',
}

function _cpHead(idx, name) {
  const num = idx ? `Контрагент №${idx}` : 'Контрагент'
  return name ? `${num} (${name})` : num
}
function fieldLabel(key, diff = null) {
  const cpName = diff?.cp_name
  const cpIdx = diff?.cp_idx
  // Для name самого контрагента "/ название" избыточно — справа уже видно old → new.
  if (key === 'counterparty_name') return _cpHead(cpIdx, cpName)
  if (key === 'counterparty_inn') return `${_cpHead(cpIdx, cpName)} / ИНН`
  if (key === 'counterparty_kpp') return `${_cpHead(cpIdx, cpName)} / КПП`
  if (FIELD_LABELS[key]) return FIELD_LABELS[key]
  const m = key.match(/^counterparty_(\d+)_(\w+)$/)
  if (m) {
    const [, mIdx, fld] = m
    const idx = cpIdx || parseInt(mIdx, 10)
    const head = _cpHead(idx, cpName)
    if (fld === 'name') return head
    return `${head} / ${CP_FIELD_LABELS[fld] || fld}`
  }
  return key
}

function issueText(err) {
  return ISSUE_TEXTS[err.code] || 'Замечание при обработке'
}

function issueFieldLabel(err) {
  return fieldLabel(err.field)
}

const llmStatus = computed(() => doc.value?.fields?.llm_status || '')
const llmFailed = computed(() => llmStatus.value.startsWith('failed') || llmStatus.value === 'disabled')

const allFieldIssues = computed(() =>
  (doc.value?.fields?.errors || []).filter((i) => i.field !== '_pipeline'),
)

const errorByField = computed(() => {
  const map = {}
  for (const e of allFieldIssues.value) map[e.field] = e
  return map
})

const hasIssues = computed(() => !llmFailed.value && allFieldIssues.value.length > 0)

const summaryText = computed(() => doc.value?.summary || '')
const summaryDetailed = computed(() => doc.value?.summary_detailed || '')

const showDetailed = ref(false)
const summaryStreaming = ref(false)
const summaryStreamText = ref('')
const summaryError = ref('')

const shortCollapsed = ref(false)
const detailedCollapsed = ref(false)

async function generateDetailedSummary() {
  showDetailed.value = true
  summaryStreaming.value = true
  summaryStreamText.value = ''
  summaryError.value = ''
  try {
    const token = localStorage.getItem('token')
    const r = await fetch(`/api/documents/${props.id}/summary`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!r.ok) {
      summaryError.value = 'Не удалось сгенерировать подробное описание'
      return
    }
    const reader = r.body.getReader()
    const decoder = new TextDecoder('utf-8')
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      summaryStreamText.value += decoder.decode(value, { stream: true })
    }
    if (summaryStreamText.value && doc.value) {
      doc.value.summary_detailed = summaryStreamText.value
    }
  } catch (e) {
    summaryError.value = 'Ошибка соединения с LLM-сервисом'
  } finally {
    summaryStreaming.value = false
  }
}

const counterparties = computed(() => doc.value?.fields?.counterparties || [])
const docDates = computed(() => (doc.value?.fields?.dates || []).filter((d) => d?.value))
const docAmounts = computed(() =>
  (doc.value?.fields?.amounts || []).filter((a) => a?.value && (a?.role === 'total' || a?.role === 'vat')),
)
const hasMultiEntity = computed(() =>
  counterparties.value.length > 0 || docDates.value.length > 0 || docAmounts.value.length > 0,
)

function rowIssue(errorKey) {
  if (!errorKey) return null
  return errorByField.value[errorKey] || null
}

const FAIL_PREFIX_LABELS = {
  parser_failed: 'Парсер не смог прочитать файл',
  kafka_failed: 'Не удалось отправить в Kafka',
  mime_unknown: 'Неизвестный формат файла',
  storage_failed: 'Ошибка сохранения файла',
}

const isFailed = computed(() => doc.value?.status === 'failed')
const failureMessage = computed(() => {
  if (!isFailed.value) return null
  const ev = audit.value.find((e) => e.status === 'error')
  const raw = ev?.message || ''
  const m = raw.match(/^([\w_]+):\s*(.+)$/s)
  if (m && FAIL_PREFIX_LABELS[m[1]]) {
    return { title: FAIL_PREFIX_LABELS[m[1]], detail: m[2] }
  }
  return { title: 'Не удалось обработать документ', detail: raw }
})

const STAGE_LABELS = {
  extract: 'Чтение файла',
  ocr: 'Распознавание скана (OCR)',
  transform: 'Извлечение полей',
  classify: 'Классификация',
  candidates: 'Сбор полей через regex',
  llm_classify: 'Классификация (LLM)',
  ner: 'Распознавание полей',
  llm: 'LLM-извлечение полей',
  reconcile: 'Сверка LLM с regex',
  validate: 'Валидация',
  normalize: 'Нормализация',
  load: 'Запись в БД',
  override: 'Ручное редактирование',
}

function stageLabel(stage) {
  return STAGE_LABELS[stage] || stage
}

function eventDot(status) {
  if (status === 'ok') return 'success'
  if (status === 'warning') return 'warning'
  if (status === 'skipped') return 'medium-emphasis'
  return 'error'
}

function eventIcon(status) {
  if (status === 'ok') return 'mdi-check-circle-outline'
  if (status === 'warning') return 'mdi-alert-outline'
  if (status === 'skipped') return 'mdi-debug-step-over'
  return 'mdi-close-circle-outline'
}

function _summarizeIssues(errs) {
  if (!Array.isArray(errs) || !errs.length) return ''
  const parts = errs.slice(0, 3).map((e) => {
    const txt = (ISSUE_TEXTS[e.code] || 'замечание').toLowerCase()
    if (e.field && e.field !== '_pipeline' && e.field !== 'document') {
      return `${fieldLabel(e.field).toLowerCase()}: ${txt}`
    }
    return txt
  })
  const more = errs.length > 3 ? `, и ещё ${errs.length - 3}` : ''
  return parts.join('; ') + more
}

function friendlyEventMessage(ev) {
  const msg = ev?.message || ''
  if (ev?.stage === 'transform' && /doc_type=|errors=|llm=/.test(msg)) {
    const parts = []
    const llmMatch = msg.match(/llm=([^,]+(?:,\s*[^,]+)?)/)
    const llmRaw = (llmMatch?.[1] || '').toLowerCase()
    if (llmRaw.startsWith('failed')) parts.push('LLM была недоступна')
    else if (llmRaw === 'disabled') parts.push('LLM была выключена')
    else if (llmRaw.startsWith('skipped')) parts.push('LLM пропущена')

    const errs = ev.payload?.errors
    if (Array.isArray(errs) && errs.length) {
      const summary = _summarizeIssues(errs)
      parts.push(`найдено замечаний: ${errs.length}${summary ? ` (${summary})` : ''}`)
    } else {
      const errsMatch = msg.match(/errors=(\d+)/)
      if (errsMatch && parseInt(errsMatch[1], 10) > 0) {
        parts.push(`найдено замечаний: ${errsMatch[1]}`)
      }
    }
    return parts.join('; ') || 'Документ обработан'
  }
  if (ev?.stage === 'load' && /status=|doc_type=|llm=|dup=/.test(msg)) {
    return 'Документ сохранён в БД'
  }
  if (ev?.stage === 'classify' && /regex_candidates|doc_type=/.test(msg)) {
    const m = msg.match(/doc_type=(\w+)/)
    return m ? `Тип документа: ${m[1]}` : 'Классификация'
  }
  if (ev?.stage === 'extract' && msg === 'reprocess_requested') {
    return 'Запрошена повторная обработка'
  }
  if (ev?.stage === 'extract' && /^parsed mime=/.test(msg)) {
    return 'Файл прочитан'
  }
  return msg
}

function isSubStage(stage) {
  return ['classify', 'llm', 'reconcile', 'validate', 'load', 'normalize', 'ner'].includes(stage)
}

function isPhaseAnchor(ev) {
  return ev.stage === 'extract' || ev.stage === 'override'
}

function phaseTitle(anchor) {
  if (anchor.stage === 'override') {
    const by = anchor.payload?.by
    return by ? `Ручное редактирование от ${by}` : 'Ручное редактирование'
  }
  const msg = anchor.message || ''
  if (msg.includes('reprocess_requested')) return 'Перепроцессинг запрошен пользователем'
  return 'Загрузка и обработка документа'
}

function phaseIcon(anchor) {
  if (anchor.stage === 'override') return 'mdi-pencil-outline'
  if ((anchor.message || '').includes('reprocess_requested')) return 'mdi-refresh'
  return 'mdi-file-upload-outline'
}

function overrideDiffLines(anchor) {
  const diffs = anchor.payload?.diffs
  if (!diffs || typeof diffs !== 'object') return []
  return Object.entries(diffs).map(([k, v]) => ({
    field: fieldLabel(k, v),
    old: v?.old ?? '—',
    new: v?.new ?? '—',
  }))
}

const phases = computed(() => {
  const result = []
  let current = null
  for (const ev of audit.value) {
    if (isPhaseAnchor(ev)) {
      if (current) result.push(current)
      current = {
        id: ev.id,
        anchor: ev,
        events: [],
        worstStatus: ev.status === 'ok' ? 'ok' : ev.status,
      }
    } else {
      if (!current) {
        current = { id: ev.id, anchor: null, events: [], worstStatus: 'ok' }
      }
      current.events.push(ev)
      if (ev.status !== 'ok' && current.worstStatus === 'ok') current.worstStatus = ev.status
      if (ev.status === 'error') current.worstStatus = 'error'
    }
  }
  if (current) result.push(current)
  return result
})

const expandedPhases = ref(new Set())
function togglePhase(id) {
  const s = new Set(expandedPhases.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  expandedPhases.value = s
}

async function openPreview() {
  previewOpen.value = true
  if (previewLoaded.value) return
  if (previewKind.value !== 'pdf' && previewKind.value !== 'image') {
    previewLoaded.value = true
    return
  }
  previewLoading.value = true
  try {
    const r = await client.get(`/documents/${props.id}/file`, { responseType: 'blob' })
    previewUrl.value = URL.createObjectURL(r.data)
    previewLoaded.value = true
  } finally {
    previewLoading.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const [d, a] = await Promise.all([
      client.get(`/documents/${props.id}`),
      client.get(`/documents/${props.id}/audit`),
    ])
    doc.value = d.data
    audit.value = a.data
    if (doc.value && !TERMINAL_STATUSES.has(doc.value.status) && !reprocessing.value) {
      reprocessing.value = true
      watchUntilTerminal().finally(() => { reprocessing.value = false })
    }
  } finally {
    loading.value = false
  }
}

async function remove() {
  deleting.value = true
  try {
    await client.delete(`/documents/${props.id}`)
    router.push('/documents')
  } finally {
    deleting.value = false
    confirmDelete.value = false
  }
}

async function download() {
  downloading.value = true
  try {
    const r = await client.get(`/documents/${props.id}/file`, { responseType: 'blob' })
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a')
    a.href = url
    a.download = doc.value.filename || 'document'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } finally {
    downloading.value = false
  }
}

const reprocessing = ref(false)
const reprocessError = ref('')
const TERMINAL_STATUSES = new Set(['loaded', 'validated_with_errors', 'failed'])

// `waiting_llm` — виртуальная стадия: extract есть, candidates ещё нет (сообщение
// в Kafka, transform-консьюмер не подхватил). Считается done, как только пришёл candidates.
const REPROCESS_STAGES = [
  { key: 'extract', label: 'Чтение файла' },
  { key: 'waiting_llm', label: 'В очереди на LLM', virtual: true, doneWhen: 'candidates' },
  { key: 'candidates', label: 'Сбор полей через regex' },
  { key: 'llm', label: 'LLM-извлечение полей' },
  { key: 'classify', label: 'Классификация' },
  { key: 'reconcile', label: 'Сверка LLM с regex' },
  { key: 'validate', label: 'Валидация' },
  { key: 'load', label: 'Запись в БД' },
]

const reprocessProgress = computed(() => {
  if (!audit.value.length) return REPROCESS_STAGES.map((s) => ({ ...s, done: false, current: false }))
  let extractIdx = -1
  for (let i = audit.value.length - 1; i >= 0; i--) {
    if (audit.value[i].stage === 'extract') { extractIdx = i; break }
  }
  const recent = extractIdx === -1 ? [] : audit.value.slice(extractIdx)
  const result = REPROCESS_STAGES.map((s) => {
    if (s.virtual) {
      const done = recent.some((e) => e.stage === s.doneWhen)
      return { ...s, done, status: null, message: '', current: false }
    }
    const ev = recent.find((e) => e.stage === s.key)
    return { ...s, done: !!ev, status: ev?.status || null, message: ev ? friendlyEventMessage(ev) : '', current: false }
  })
  const firstUndone = result.findIndex((s) => !s.done)
  if (firstUndone >= 0) result[firstUndone].current = true
  return result
})

const liveSubstage = computed(() => {
  const s = doc.value?.status
  if (!s || TERMINAL_STATUSES.has(s)) return null
  const steps = reprocessProgress.value
  if (steps.find((x) => x.key === 'candidates')?.done && !steps.find((x) => x.key === 'llm')?.done) {
    return 'llm_running'
  }
  if (steps.find((x) => x.key === 'extract')?.done && !steps.find((x) => x.key === 'candidates')?.done) {
    return 'waiting_llm'
  }
  return null
})

const reprocessChip = computed(() => {
  const sub = liveSubstage.value
  if (sub && SUBSTAGE_META[sub]) return SUBSTAGE_META[sub]
  return { label: 'Обрабатывается', color: 'info', icon: 'mdi-cog-sync-outline' }
})

async function pollOnce() {
  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), 3000)
  try {
    const [d, a] = await Promise.all([
      client.get(`/documents/${props.id}`, { signal: ctrl.signal }),
      client.get(`/documents/${props.id}/audit`, { signal: ctrl.signal }),
    ])
    doc.value = d.data
    audit.value = a.data
    return true
  } catch (e) {
    console.warn('[poll]', e?.message || e)
    return false
  } finally {
    clearTimeout(t)
  }
}

function _currentRunHasLoadEvent() {
  const ev = audit.value || []
  let extractIdx = -1
  for (let i = ev.length - 1; i >= 0; i--) {
    if (ev[i].stage === 'extract') { extractIdx = i; break }
  }
  if (extractIdx < 0) return false
  for (let i = extractIdx; i < ev.length; i++) {
    if (ev[i].stage === 'load') return true
  }
  return false
}

async function watchUntilTerminal(timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline && reprocessing.value) {
    await new Promise((r) => setTimeout(r, 50))
    if (!reprocessing.value) return
    await pollOnce()
    if (doc.value?.status === 'failed') return
    if (_currentRunHasLoadEvent()) return
  }
}

function dismissReprocessing() {
  reprocessing.value = false
}

async function reprocessDocument() {
  reprocessing.value = true
  reprocessError.value = ''
  try {
    await client.post(`/documents/${props.id}/reprocess`)
    await pollOnce()
    await watchUntilTerminal()
  } catch (e) {
    reprocessError.value = e?.response?.data?.detail || e?.message || 'Не удалось перепроцессить'
  } finally {
    reprocessing.value = false
  }
}

const editing = ref(false)
const editSaving = ref(false)
const editError = ref('')
const editValues = ref({})

const INN_RE = /^\d{10}$|^\d{12}$/
const KPP_RE = /^\d{4}[\dA-Z]{2}\d{3}$/i

function validateInn(v) {
  if (!v) return null
  return INN_RE.test(v.trim()) ? null : 'ИНН: ровно 10 или 12 цифр'
}
function validateKpp(v) {
  if (!v) return null
  return KPP_RE.test(v.trim()) ? null : 'КПП: 9 символов (например, 770101001)'
}
function validateDate(v) {
  if (!v) return null
  const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!m) return 'Дата: формат YYYY-MM-DD'
  const y = parseInt(m[1], 10)
  if (y < 1900 || y > 2100) return 'Год вне диапазона 1900–2100'
  return null
}
function validateVat(v) {
  if (v === '' || v === null || v === undefined) return null
  const n = Number(String(v).replace(',', '.'))
  if (!Number.isFinite(n)) return 'Ставка НДС: число'
  if (n < 0 || n > 100) return 'Ставка НДС: 0–100'
  return null
}
function validateNumeric(v) {
  if (v === '' || v === null || v === undefined) return null
  const n = Number(String(v).replace(',', '.').replace(/\s/g, ''))
  return Number.isFinite(n) ? null : 'Должно быть числом'
}

const editErrors = computed(() => ({
  doc_date: validateDate(editValues.value.doc_date),
  counterparty_inn: validateInn(editValues.value.counterparty_inn),
  counterparty_kpp: validateKpp(editValues.value.counterparty_kpp),
  amount_total: validateNumeric(editValues.value.amount_total),
  vat_rate: validateVat(editValues.value.vat_rate),
}))
const editHasErrors = computed(() => Object.values(editErrors.value).some(Boolean))

const cpEditing = ref(false)
const cpSaving = ref(false)
const cpError = ref('')
const cpDraft = ref([])

const cpRowErrors = computed(() => cpDraft.value.map((c) => ({
  inn: validateInn(c.inn),
  kpp: validateKpp(c.kpp),
})))
const cpHasErrors = computed(() => cpRowErrors.value.some((e) => e.inn || e.kpp))

const CP_FORM_OPTIONS = ['ООО', 'ОАО', 'ЗАО', 'ИП', 'ПАО', 'АО']

function startCpEdit() {
  cpDraft.value = (counterparties.value || []).map((c) => ({
    name: c.name || '',
    inn: c.inn || '',
    kpp: c.kpp || '',
    form: c.form || '',
    role: c.role || '',
    is_primary: !!c.is_primary,
  }))
  if (!cpDraft.value.length) {
    cpDraft.value.push({ name: '', inn: '', kpp: '', form: '', role: '', is_primary: true })
  }
  cpError.value = ''
  cpEditing.value = true
}
function cancelCpEdit() {
  cpEditing.value = false
  cpError.value = ''
}
function addCpRow() {
  cpDraft.value.push({ name: '', inn: '', kpp: '', form: '', role: '', is_primary: false })
}
function removeCpRow(idx) {
  const wasPrimary = cpDraft.value[idx]?.is_primary
  cpDraft.value.splice(idx, 1)
  if (wasPrimary && cpDraft.value.length) cpDraft.value[0].is_primary = true
}
function setPrimary(idx) {
  cpDraft.value.forEach((c, i) => { c.is_primary = i === idx })
}
async function saveCpEdit() {
  cpSaving.value = true
  cpError.value = ''
  try {
    const payload = cpDraft.value
      .filter((c) => (c.name || '').trim() || (c.inn || '').trim())
      .map((c) => ({
        name: c.name?.trim() || null,
        inn: c.inn?.trim() || null,
        kpp: c.kpp?.trim() || null,
        form: c.form?.trim() || null,
        role: c.role?.trim() || null,
        is_primary: !!c.is_primary,
      }))
    const r = await client.patch(`/documents/${props.id}`, { fields: { counterparties: payload } })
    doc.value = r.data
    const a = await client.get(`/documents/${props.id}/audit`)
    audit.value = a.data
    cpEditing.value = false
  } catch (e) {
    cpError.value = e?.response?.data?.detail || e?.message || 'Не удалось сохранить контрагентов'
  } finally {
    cpSaving.value = false
  }
}

const DOC_TYPE_OPTIONS = [
  { value: '', title: '— не определён —' },
  { value: 'invoice', title: 'Счёт-фактура' },
  { value: 'act', title: 'Акт' },
  { value: 'contract', title: 'Договор' },
  { value: 'waybill', title: 'ТОРГ-12 (накладная)' },
  { value: 'upd', title: 'УПД' },
  { value: 'payment_order', title: 'Платёжное поручение' },
]

function startEdit() {
  const d = doc.value || {}
  editValues.value = {
    doc_type: d.doc_type || '',
    number: d.number || '',
    doc_date: d.doc_date || '',
    counterparty_name: d.counterparty_name || '',
    counterparty_inn: d.counterparty_inn || '',
    counterparty_kpp: d.counterparty_kpp || '',
    amount_total: d.amount_total ?? '',
    vat_rate: d.vat_rate ?? '',
  }
  editError.value = ''
  editing.value = true
}

function cancelEdit() {
  editing.value = false
  editError.value = ''
}

async function saveEdit() {
  editSaving.value = true
  editError.value = ''
  try {
    const r = await client.patch(`/documents/${props.id}`, { fields: editValues.value })
    doc.value = r.data
    const a = await client.get(`/documents/${props.id}/audit`)
    audit.value = a.data
    editing.value = false
  } catch (e) {
    editError.value = e?.response?.data?.detail || e?.message || 'Не удалось сохранить изменения'
  } finally {
    editSaving.value = false
  }
}

onBeforeUnmount(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
})

onMounted(load)
</script>

<template>
  <div v-if="doc">
    <div class="page-header d-flex flex-wrap align-center" style="gap:12px">
      <v-btn
        icon="mdi-arrow-left"
        variant="text"
        size="small"
        @click="router.push('/documents')"
      />
      <div style="min-width:0;flex:1">
        <h1 class="page-title" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ doc.filename }}</h1>
        <div class="d-flex align-center mt-1" style="gap:8px;flex-wrap:wrap">
          <v-chip
            v-if="reprocessing"
            size="small"
            variant="tonal"
            :color="reprocessChip.color"
            :prepend-icon="reprocessChip.icon"
          >
            {{ reprocessChip.label }}
          </v-chip>
          <v-chip
            v-else
            size="small"
            variant="tonal"
            :color="statusColor(doc.status)"
            :prepend-icon="statusIcon(doc.status)"
          >
            {{ statusLabel(doc.status) }}
          </v-chip>
          <v-chip v-if="doc.doc_type" size="small" variant="tonal" color="primary">
            {{ formatDocType(doc.doc_type) }}
          </v-chip>
          <span class="text-caption text-medium-emphasis">{{ formatDateTime(doc.created_at) }}</span>
        </div>
      </div>
      <v-btn
        color="primary"
        variant="tonal"
        prepend-icon="mdi-file-eye-outline"
        @click="openPreview"
      >
        Предпросмотр
      </v-btn>
      <v-btn
        :loading="downloading"
        prepend-icon="mdi-download-outline"
        variant="tonal"
        @click="download"
      >
        Скачать
      </v-btn>
      <v-btn
        v-if="!isFailed"
        :loading="reprocessing"
        prepend-icon="mdi-refresh"
        variant="tonal"
        :disabled="!doc.text_content"
        @click="reprocessDocument"
      >
        Перепроцессить
      </v-btn>
      <v-btn
        color="error"
        variant="tonal"
        prepend-icon="mdi-delete-outline"
        @click="confirmDelete = true"
      >
        Удалить
      </v-btn>
    </div>

    <v-alert
      v-if="isFailed"
      type="error"
      variant="tonal"
      class="mb-4"
      border="start"
    >
      <div style="font-weight:600;margin-bottom:4px">{{ failureMessage.title }}</div>
      <div v-if="failureMessage.detail" style="font-size:13.5px" class="mono">{{ failureMessage.detail }}</div>
      <div class="text-caption text-medium-emphasis mt-2">
        Извлечение полей не запускалось — нет смысла без прочитанного содержимого.
      </div>
    </v-alert>

    <v-alert
      v-else-if="reprocessing"
      type="info"
      variant="tonal"
      class="mb-4"
      border="start"
      icon="mdi-cog-sync-outline"
    >
      <div class="d-flex align-center" style="gap:12px">
        <v-progress-circular indeterminate size="20" width="2" color="info" />
        <div style="font-weight:600;font-size:14px">{{ reprocessChip.label }}…</div>
        <v-spacer />
        <v-btn
          size="x-small"
          variant="text"
          icon="mdi-close"
          title="Скрыть индикатор"
          @click="dismissReprocessing"
        />
      </div>
      <div class="reprocess-checklist mt-3">
        <div
          v-for="step in reprocessProgress"
          :key="step.key"
          class="reprocess-step"
          :class="{ 'is-done': step.done, 'is-current': step.current }"
        >
          <v-icon
            v-if="step.done && step.status === 'warning'"
            icon="mdi-alert-circle"
            color="warning"
            size="16"
          />
          <v-icon
            v-else-if="step.done && step.status === 'error'"
            icon="mdi-close-circle"
            color="error"
            size="16"
          />
          <v-icon
            v-else-if="step.done && step.status === 'skipped'"
            icon="mdi-debug-step-over"
            color="medium-emphasis"
            size="16"
          />
          <v-icon
            v-else-if="step.done"
            icon="mdi-check-circle"
            color="success"
            size="16"
          />
          <v-progress-circular
            v-else-if="step.current"
            indeterminate
            size="14"
            width="2"
            color="info"
          />
          <v-icon
            v-else
            icon="mdi-circle-outline"
            color="medium-emphasis"
            size="16"
          />
          <span class="step-label">{{ step.label }}</span>
          <span v-if="step.message" class="step-msg">— {{ step.message }}</span>
        </div>
      </div>
    </v-alert>

    <v-alert
      v-else-if="llmFailed"
      type="warning"
      variant="tonal"
      class="mb-4"
      border="start"
      icon="mdi-robot-off-outline"
    >
      <div style="font-weight:600;margin-bottom:4px">LLM была недоступна — поля не извлечены</div>
      <div style="font-size:13.5px;margin-bottom:8px">
        Содержимое документа сохранено, но извлечение полей не запускалось без LLM-сервиса.
        Когда сервис снова работает, нажмите «Перепроцессить».
      </div>
      <v-btn
        size="small"
        variant="tonal"
        color="warning"
        prepend-icon="mdi-refresh"
        :loading="reprocessing"
        @click="reprocessDocument"
      >
        Перепроцессить
      </v-btn>
      <div v-if="reprocessError" class="text-caption text-error mt-2">
        {{ reprocessError }}
      </div>
    </v-alert>

    <v-alert
      v-if="!isFailed && !llmFailed && !reprocessing && hasIssues"
      type="warning"
      variant="tonal"
      class="mb-4"
      border="start"
    >
      <div style="font-weight:600;margin-bottom:6px">Документ обработан с предупреждениями</div>
      <ul style="margin:0;padding-left:0;list-style:none;font-size:13.5px">
        <li
          v-for="(iss, i) in allFieldIssues"
          :key="i"
          style="margin-top:4px;display:flex;align-items:start;gap:8px"
        >
          <v-icon icon="mdi-alert-outline" color="warning" size="16" style="margin-top:2px;flex-shrink:0" />
          <div>
            <strong>{{ issueFieldLabel(iss) }}:</strong>
            {{ issueText(iss) }}
            <span v-if="iss.value" class="text-medium-emphasis">— «{{ iss.value }}»</span>
          </div>
        </li>
      </ul>
    </v-alert>

    <v-row>
      <v-col cols="12" md="6">
        <v-card class="app-card" style="height:100%">
          <v-card-text class="pa-5">
            <div class="d-flex align-center mb-3" style="gap:8px">
              <v-icon size="18" color="primary">mdi-file-document-outline</v-icon>
              <span class="text-subtitle-2" style="font-weight:600">Сведения</span>
              <v-spacer />
              <v-tooltip v-if="!editing && !isFailed" location="top" text="Поправить значения вручную (HITL)">
                <template #activator="{ props }">
                  <v-btn
                    v-bind="props"
                    size="x-small"
                    variant="text"
                    color="primary"
                    prepend-icon="mdi-pencil-outline"
                    @click="startEdit"
                  >
                    Редактировать
                  </v-btn>
                </template>
              </v-tooltip>
            </div>

            <div v-if="!editing">
              <div v-for="row in infoRows" :key="row.label" class="info-row">
                <div class="info-row-label d-flex align-center" style="gap:6px">
                  <span>{{ row.label }}</span>
                  <v-tooltip v-if="rowIssue(row.errorKey)" location="top">
                    <template #activator="{ props }">
                      <v-icon v-bind="props" size="14" color="warning">mdi-alert-outline</v-icon>
                    </template>
                    {{ issueText(rowIssue(row.errorKey)) }}
                  </v-tooltip>
                </div>
                <div
                  class="info-row-value"
                  :class="{
                    mono: row.mono && row.value !== '—',
                    'text-warning': errorByField[row.errorKey],
                  }"
                >
                  {{ row.value }}
                </div>
              </div>
            </div>

            <div v-else class="d-flex flex-column" style="gap:10px">
              <v-select
                v-model="editValues.doc_type"
                :items="DOC_TYPE_OPTIONS"
                label="Тип документа"
                density="compact"
                variant="outlined"
                hide-details
              />
              <v-text-field
                v-model="editValues.number"
                label="Номер"
                density="compact"
                variant="outlined"
                hide-details
              />
              <v-text-field
                v-model="editValues.doc_date"
                label="Дата документа"
                placeholder="YYYY-MM-DD"
                density="compact"
                variant="outlined"
                type="date"
                :error-messages="editErrors.doc_date || []"
                :hide-details="!editErrors.doc_date"
              />
              <v-text-field
                v-model="editValues.counterparty_name"
                label="Контрагент"
                density="compact"
                variant="outlined"
                hide-details
              />
              <div class="d-flex align-start" style="gap:10px">
                <v-text-field
                  v-model="editValues.counterparty_inn"
                  label="ИНН"
                  density="compact"
                  variant="outlined"
                  :error-messages="editErrors.counterparty_inn || []"
                  :hide-details="!editErrors.counterparty_inn"
                />
                <v-text-field
                  v-model="editValues.counterparty_kpp"
                  label="КПП"
                  density="compact"
                  variant="outlined"
                  :error-messages="editErrors.counterparty_kpp || []"
                  :hide-details="!editErrors.counterparty_kpp"
                />
              </div>
              <div class="d-flex align-start" style="gap:10px">
                <v-text-field
                  v-model="editValues.amount_total"
                  label="Итоговая сумма"
                  density="compact"
                  variant="outlined"
                  :error-messages="editErrors.amount_total || []"
                  :hide-details="!editErrors.amount_total"
                />
                <v-text-field
                  v-model="editValues.vat_rate"
                  label="Ставка НДС, %"
                  density="compact"
                  variant="outlined"
                  :error-messages="editErrors.vat_rate || []"
                  :hide-details="!editErrors.vat_rate"
                />
              </div>

              <v-alert v-if="editError" type="error" variant="tonal" density="compact" class="mt-1">
                {{ editError }}
              </v-alert>

              <div class="d-flex justify-end mt-2" style="gap:8px">
                <v-btn size="small" variant="text" :disabled="editSaving" @click="cancelEdit">
                  Отмена
                </v-btn>
                <v-btn
                  size="small"
                  color="primary"
                  variant="flat"
                  prepend-icon="mdi-content-save-outline"
                  :loading="editSaving"
                  :disabled="editHasErrors"
                  @click="saveEdit"
                >
                  Сохранить
                </v-btn>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="6">
        <v-card v-if="!llmFailed" class="app-card" style="height:100%">
          <v-card-text class="pa-5 d-flex flex-column" style="height:100%">
            <div class="d-flex align-center mb-3" style="gap:10px;flex-wrap:wrap">
              <v-icon size="18" color="info">mdi-text-short</v-icon>
              <span class="text-subtitle-2" style="font-weight:600">Краткое описание документа</span>
              <v-spacer />
              <v-progress-circular
                v-if="summaryStreaming"
                indeterminate
                size="18"
                width="2"
                color="primary"
              />
              <v-btn
                v-if="summaryText || summaryDetailed || summaryStreamText"
                :icon="shortCollapsed ? 'mdi-chevron-down' : 'mdi-chevron-up'"
                variant="text"
                size="x-small"
                :title="shortCollapsed ? 'Развернуть' : 'Свернуть'"
                @click="shortCollapsed = !shortCollapsed"
              />
            </div>
            <div v-if="!shortCollapsed && summaryText" style="font-size:14px;line-height:1.55">{{ summaryText }}</div>
            <div v-else-if="!shortCollapsed" class="text-medium-emphasis" style="font-size:14px">
              LLM не вернула резюме при обработке.
            </div>

            <v-divider v-if="showDetailed || summaryDetailed" class="my-3" />

            <div v-if="showDetailed || summaryDetailed">
              <div class="d-flex align-center mb-3" style="gap:10px;flex-wrap:wrap">
                <v-icon size="18" color="info">mdi-text-long</v-icon>
                <span class="text-subtitle-2" style="font-weight:600">Подробное описание документа</span>
                <v-spacer />
                <v-tooltip v-if="!summaryStreaming && !isFailed" location="top" text="Запросит у LLM новое подробное описание">
                  <template #activator="{ props }">
                    <v-btn
                      v-bind="props"
                      size="x-small"
                      variant="text"
                      color="primary"
                      prepend-icon="mdi-robot-outline"
                      @click="generateDetailedSummary"
                    >
                      Перегенерировать
                    </v-btn>
                  </template>
                </v-tooltip>
                <v-btn
                  :icon="detailedCollapsed ? 'mdi-chevron-down' : 'mdi-chevron-up'"
                  variant="text"
                  size="x-small"
                  :title="detailedCollapsed ? 'Развернуть' : 'Свернуть'"
                  @click="detailedCollapsed = !detailedCollapsed"
                />
              </div>
              <div v-if="!detailedCollapsed">
                <div v-if="summaryError" class="text-error" style="font-size:14px">{{ summaryError }}</div>
                <div v-else-if="summaryStreaming || summaryStreamText" style="font-size:14px;line-height:1.55;white-space:pre-wrap">
                  {{ summaryStreamText }}<span v-if="summaryStreaming" class="cursor-blink">▌</span>
                </div>
                <div v-else-if="summaryDetailed" style="font-size:14px;line-height:1.55;white-space:pre-wrap">{{ summaryDetailed }}</div>
              </div>
            </div>

            <div v-else-if="!isFailed" class="mt-auto pt-3">
              <v-tooltip location="top" text="Запросит у LLM подробное описание документа">
                <template #activator="{ props }">
                  <v-btn
                    v-bind="props"
                    size="small"
                    variant="tonal"
                    color="primary"
                    prepend-icon="mdi-robot-outline"
                    :disabled="!doc.text_content"
                    @click="generateDetailedSummary"
                  >
                    Подробнее (LLM)
                  </v-btn>
                </template>
              </v-tooltip>
            </div>
          </v-card-text>
        </v-card>

        <v-card v-else class="app-card" style="height:100%">
          <v-card-text class="pa-5 d-flex flex-column align-center justify-center" style="height:100%;min-height:180px">
            <v-icon size="32" color="medium-emphasis" class="mb-2">mdi-text-short</v-icon>
            <div class="text-caption text-medium-emphasis">Резюме недоступно — LLM-сервис не сработал</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-card v-if="hasMultiEntity || cpEditing" class="app-card mt-4">
      <v-card-text class="pa-5">
        <div class="d-flex align-center mb-4" style="gap:8px">
          <v-icon size="18" color="primary">mdi-account-group-outline</v-icon>
          <span class="text-subtitle-2" style="font-weight:600">Извлечённая информация</span>
          <v-chip
            v-if="counterparties.length"
            size="x-small"
            variant="tonal"
            color="primary"
          >
            {{ counterparties.length }} контр.
          </v-chip>
          <v-spacer />
          <v-btn
            v-if="!cpEditing && !isFailed"
            size="x-small"
            variant="text"
            color="primary"
            prepend-icon="mdi-account-edit-outline"
            @click="startCpEdit"
          >
            Редактировать контрагентов
          </v-btn>
        </div>

        <div v-if="!cpEditing && counterparties.length" class="mb-5">
          <div class="text-caption text-medium-emphasis mb-2" style="text-transform:uppercase;letter-spacing:.04em">
            Контрагенты
          </div>
          <div class="d-flex flex-column" style="gap:10px">
            <div
              v-for="(cp, i) in counterparties"
              :key="i"
              class="cp-card"
              :class="{ 'cp-card-primary': cp.is_primary }"
            >
              <div class="d-flex align-center mb-2" style="gap:8px;flex-wrap:wrap">
                <span class="cp-index">№{{ i + 1 }}</span>
                <v-chip
                  v-if="cp.form"
                  size="x-small"
                  variant="tonal"
                  color="secondary"
                  class="mono"
                >
                  {{ cp.form }}
                </v-chip>
                <span style="font-weight:600;font-size:14px">{{ cp.name || '—' }}</span>
                <v-chip
                  v-if="cp.role"
                  size="x-small"
                  variant="tonal"
                  color="primary"
                >
                  {{ cp.role }}
                </v-chip>
                <v-chip
                  v-if="cp.is_primary"
                  size="x-small"
                  variant="tonal"
                  color="success"
                  prepend-icon="mdi-star"
                >
                  основной
                </v-chip>
              </div>
              <div class="d-flex" style="gap:24px;flex-wrap:wrap;font-size:13px">
                <div>
                  <span class="text-medium-emphasis">ИНН:&nbsp;</span>
                  <span class="mono">{{ cp.inn || '—' }}</span>
                </div>
                <div>
                  <span class="text-medium-emphasis">КПП:&nbsp;</span>
                  <span class="mono">{{ cp.kpp || '—' }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="cpEditing" class="mb-5">
          <div class="text-caption text-medium-emphasis mb-2" style="text-transform:uppercase;letter-spacing:.04em">
            Контрагенты — редактирование
          </div>
          <div class="d-flex flex-column" style="gap:12px">
            <div
              v-for="(cp, i) in cpDraft"
              :key="i"
              class="cp-card"
              :class="{ 'cp-card-primary': cp.is_primary }"
            >
              <div class="d-flex align-center mb-2" style="gap:8px;flex-wrap:wrap">
                <span class="cp-index">№{{ i + 1 }}</span>
                <v-chip
                  v-if="cp.is_primary"
                  size="x-small"
                  variant="tonal"
                  color="success"
                  prepend-icon="mdi-star"
                >
                  основной
                </v-chip>
                <v-btn
                  v-else
                  size="x-small"
                  variant="tonal"
                  prepend-icon="mdi-star-outline"
                  @click="setPrimary(i)"
                >
                  Сделать основным
                </v-btn>
                <v-spacer />
                <v-btn
                  v-if="cpDraft.length > 1"
                  icon="mdi-trash-can-outline"
                  size="x-small"
                  variant="text"
                  color="error"
                  title="Удалить контрагента"
                  @click="removeCpRow(i)"
                />
              </div>
              <div class="d-flex flex-wrap" style="gap:8px">
                <v-text-field
                  v-model="cp.name"
                  label="Название"
                  density="compact"
                  variant="outlined"
                  hide-details
                  style="flex:1 1 260px"
                />
                <v-combobox
                  v-model="cp.form"
                  :items="CP_FORM_OPTIONS"
                  label="Форма"
                  density="compact"
                  variant="outlined"
                  hide-details
                  style="flex:0 0 110px"
                />
              </div>
              <div class="d-flex flex-wrap align-start mt-2" style="gap:8px">
                <v-text-field
                  v-model="cp.inn"
                  label="ИНН"
                  density="compact"
                  variant="outlined"
                  :error-messages="cpRowErrors[i]?.inn || []"
                  :hide-details="!cpRowErrors[i]?.inn"
                  style="flex:1 1 140px"
                />
                <v-text-field
                  v-model="cp.kpp"
                  label="КПП"
                  density="compact"
                  variant="outlined"
                  :error-messages="cpRowErrors[i]?.kpp || []"
                  :hide-details="!cpRowErrors[i]?.kpp"
                  style="flex:1 1 130px"
                />
                <v-text-field
                  v-model="cp.role"
                  label="Роль (продавец, покупатель…)"
                  density="compact"
                  variant="outlined"
                  hide-details
                  style="flex:1 1 200px"
                />
              </div>
            </div>
          </div>

          <v-alert v-if="cpError" type="error" variant="tonal" density="compact" class="mt-3">
            {{ cpError }}
          </v-alert>

          <div class="d-flex justify-space-between mt-3" style="gap:8px;flex-wrap:wrap">
            <v-btn
              size="small"
              variant="tonal"
              prepend-icon="mdi-account-plus-outline"
              @click="addCpRow"
            >
              Добавить контрагента
            </v-btn>
            <div class="d-flex" style="gap:8px">
              <v-btn size="small" variant="text" :disabled="cpSaving" @click="cancelCpEdit">Отмена</v-btn>
              <v-btn
                size="small"
                color="primary"
                variant="flat"
                prepend-icon="mdi-content-save-outline"
                :loading="cpSaving"
                :disabled="cpHasErrors"
                @click="saveCpEdit"
              >
                Сохранить
              </v-btn>
            </div>
          </div>
        </div>

        <v-row v-if="docDates.length || docAmounts.length" no-gutters style="gap:24px;flex-wrap:wrap">
          <v-col v-if="docDates.length" cols="12" sm="5">
            <div class="text-caption text-medium-emphasis mb-2" style="text-transform:uppercase;letter-spacing:.04em">
              Даты ({{ docDates.length }})
            </div>
            <div class="d-flex flex-column" style="gap:6px">
              <div v-for="(d, i) in docDates" :key="i" class="entity-row">
                <v-chip size="x-small" variant="tonal" color="info">
                  {{ dateRoleLabel(d.role) }}
                </v-chip>
                <span class="mono">{{ d.value }}</span>
              </div>
            </div>
          </v-col>
          <v-col v-if="docAmounts.length" cols="12" sm="5">
            <div class="text-caption text-medium-emphasis mb-2" style="text-transform:uppercase;letter-spacing:.04em">
              Суммы ({{ docAmounts.length }})
            </div>
            <div class="d-flex flex-column" style="gap:6px">
              <div v-for="(a, i) in docAmounts" :key="i" class="entity-row">
                <v-chip size="x-small" variant="tonal" color="success">
                  {{ amountRoleLabel(a.role) }}
                </v-chip>
                <span class="mono">{{ formatAmount(a.value, doc.currency) }}</span>
              </div>
            </div>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-card class="app-card mt-4">
      <v-tabs v-model="tab" color="primary" align-tabs="start" density="comfortable">
        <v-tab value="text" prepend-icon="mdi-text-box-outline">Извлечённый текст</v-tab>
        <v-tab value="fields" prepend-icon="mdi-code-json">Извлечённые поля</v-tab>
        <v-tab value="audit" prepend-icon="mdi-history">Аудит-трейл</v-tab>
        <v-tab value="tech" prepend-icon="mdi-cog-outline">Технические данные</v-tab>
      </v-tabs>
      <v-divider />
      <v-card-text class="pa-5">
        <v-window v-model="tab">
          <v-window-item value="text">
            <pre v-if="doc.text_content" class="text-block" style="max-height:520px">{{ doc.text_content }}</pre>
            <div v-else class="empty-state">
              <v-icon>mdi-file-question-outline</v-icon>
              <div class="text-body-2">Текст не извлечён</div>
            </div>
          </v-window-item>
          <v-window-item value="fields">
            <pre v-if="doc.fields" class="json-block" style="max-height:520px">{{ JSON.stringify(doc.fields, null, 2) }}</pre>
            <div v-else class="empty-state">
              <v-icon>mdi-help-circle-outline</v-icon>
              <div class="text-body-2">Поля не извлечены</div>
            </div>
          </v-window-item>
          <v-window-item value="audit">
            <div v-if="!phases.length" class="empty-state">
              <v-icon>mdi-history</v-icon>
              <div class="text-body-2">Событий пока нет</div>
            </div>
            <div v-else class="d-flex flex-column" style="gap:10px">
              <div
                v-for="phase in phases"
                :key="phase.id"
                class="audit-phase"
                :class="{ 'is-expanded': expandedPhases.has(phase.id), 'is-clickable': phase.events.length > 0 }"
              >
                <div
                  class="audit-phase-header"
                  @click="phase.events.length && togglePhase(phase.id)"
                >
                  <v-icon
                    :icon="phase.anchor ? phaseIcon(phase.anchor) : 'mdi-cog-outline'"
                    :color="eventDot(phase.worstStatus)"
                    size="20"
                  />
                  <div style="flex:1;min-width:0">
                    <div class="d-flex align-center flex-wrap" style="gap:8px">
                      <span class="text-body-2" style="font-weight:600">
                        {{ phase.anchor ? phaseTitle(phase.anchor) : 'Обработка' }}
                      </span>
                      <v-chip
                        v-if="phase.worstStatus !== 'ok'"
                        size="x-small"
                        variant="tonal"
                        :color="eventDot(phase.worstStatus)"
                      >
                        {{ phase.worstStatus === 'warning' ? 'с замечаниями' : 'с ошибкой' }}
                      </v-chip>
                    </div>
                    <div class="text-caption text-medium-emphasis mt-1">
                      {{ phase.anchor ? formatDateTime(phase.anchor.created_at) : formatDateTime(phase.events[0]?.created_at) }}
                    </div>
                  </div>
                  <v-icon
                    v-if="phase.events.length"
                    :icon="expandedPhases.has(phase.id) ? 'mdi-chevron-up' : 'mdi-chevron-down'"
                    size="20"
                    color="medium-emphasis"
                  />
                </div>

                <div
                  v-if="phase.anchor && phase.anchor.stage === 'override'"
                  class="audit-phase-override-body"
                >
                  <div
                    v-for="(d, i) in overrideDiffLines(phase.anchor)"
                    :key="i"
                    class="override-diff-row"
                  >
                    <span class="override-field">{{ d.field }}:</span>
                    <span class="override-old">{{ d.old }}</span>
                    <v-icon icon="mdi-arrow-right" size="14" color="medium-emphasis" />
                    <span class="override-new">{{ d.new }}</span>
                  </div>
                </div>

                <div
                  v-if="phase.events.length && expandedPhases.has(phase.id)"
                  class="audit-phase-body"
                >
                  <div
                    v-for="(ev, i) in phase.events"
                    :key="ev.id"
                    class="audit-substage"
                  >
                    <v-icon
                      :icon="eventIcon(ev.status)"
                      :color="eventDot(ev.status)"
                      size="16"
                    />
                    <div style="flex:1;min-width:0">
                      <div class="d-flex align-center flex-wrap" style="gap:6px">
                        <span class="text-body-2" style="font-weight:500">{{ stageLabel(ev.stage) }}</span>
                        <span class="text-caption text-medium-emphasis">{{ formatDateTime(ev.created_at) }}</span>
                      </div>
                      <div v-if="friendlyEventMessage(ev)" class="text-caption text-medium-emphasis mt-1" style="line-height:1.45">
                        {{ friendlyEventMessage(ev) }}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </v-window-item>
          <v-window-item value="tech">
            <div class="info-row">
              <div class="info-row-label">doc_id</div>
              <div class="info-row-value mono">{{ doc.doc_id }}</div>
            </div>
            <div class="info-row">
              <div class="info-row-label">MIME</div>
              <div class="info-row-value mono">{{ doc.mime_type || '—' }}</div>
            </div>
            <div class="info-row">
              <div class="info-row-label">Размер</div>
              <div class="info-row-value">{{ formatBytes(doc.size_bytes) }}</div>
            </div>
            <div class="info-row">
              <div class="info-row-label">SHA-256</div>
              <div class="info-row-value mono">{{ doc.sha256 }}</div>
            </div>
            <div v-if="doc.storage_path" class="info-row">
              <div class="info-row-label">Storage path</div>
              <div class="info-row-value mono">{{ doc.storage_path }}</div>
            </div>
          </v-window-item>
        </v-window>
      </v-card-text>
    </v-card>

    <v-dialog
      v-model="previewOpen"
      :fullscreen="previewFullscreen"
      :content-class="previewFullscreen ? 'preview-dialog-fs' : 'preview-dialog-content'"
      scrollable
    >
      <v-card class="app-card preview-card">
        <div class="preview-header">
          <v-icon size="18" color="medium-emphasis">mdi-file-eye-outline</v-icon>
          <span class="text-subtitle-2" style="font-weight:600">Предпросмотр</span>
          <span class="text-caption text-medium-emphasis" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:340px">
            {{ doc.filename }}
          </span>
          <v-spacer />
          <span class="text-caption text-medium-emphasis mono">{{ doc.mime_type || '—' }}</span>
          <v-btn
            :icon="previewFullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'"
            variant="text"
            size="small"
            :title="previewFullscreen ? 'Свернуть' : 'На весь экран'"
            @click="previewFullscreen = !previewFullscreen"
          />
          <v-btn icon="mdi-close" variant="text" size="small" @click="previewOpen = false" />
        </div>
        <div class="preview-body">
          <iframe
            v-if="previewKind === 'pdf' && previewUrl"
            :src="previewUrl"
            class="preview-frame"
            :title="doc.filename"
          />
          <img
            v-else-if="previewKind === 'image' && previewUrl"
            :src="previewUrl"
            class="preview-image"
            :alt="doc.filename"
          />
          <div v-else-if="previewKind === 'text' && doc.text_content" class="preview-text">
            <div class="preview-text-hint">
              <v-icon size="16">mdi-information-outline</v-icon>
              <span>Браузер не умеет рендерить <strong>{{ extOf(doc.filename) }}</strong> напрямую — показан извлечённый текст</span>
            </div>
            <pre>{{ doc.text_content }}</pre>
          </div>
          <div
            v-else-if="!previewLoading"
            class="empty-state"
            style="height:100%;display:flex;flex-direction:column;justify-content:center"
          >
            <v-icon size="48">mdi-file-question-outline</v-icon>
            <div class="text-body-2 mt-2">Превью недоступно</div>
            <div class="text-caption mt-1">Скачайте оригинал, чтобы посмотреть содержимое</div>
          </div>
          <v-progress-circular
            v-if="previewLoading"
            indeterminate
            color="primary"
            class="preview-loader"
          />
        </div>
      </v-card>
    </v-dialog>

    <v-dialog v-model="confirmDelete" max-width="460">
      <v-card class="app-card">
        <v-card-title class="pt-5 px-5">Удалить документ?</v-card-title>
        <v-card-text class="px-5">
          <code>{{ doc.filename }}</code> и весь аудит-трейл будут удалены безвозвратно.
          Если других документов с таким же содержимым нет — удалится и файл.
        </v-card-text>
        <v-card-actions class="px-5 pb-5">
          <v-spacer />
          <v-btn variant="text" @click="confirmDelete = false">Отмена</v-btn>
          <v-btn color="error" :loading="deleting" @click="remove">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>

  <div v-else-if="loading" class="d-flex justify-center pa-12">
    <v-progress-circular indeterminate color="primary" />
  </div>
</template>
