const dtFormat = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow',
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

export function formatDateTime(value) {
  if (!value) return ''
  const d = value instanceof Date ? value : new Date(value)
  if (isNaN(d.getTime())) return String(value)
  return dtFormat.format(d) + ' МСК'
}

export const DOC_TYPE_LABELS = {
  invoice: 'Счёт-фактура',
  act: 'Акт',
  contract: 'Договор',
  payment_order: 'Платёжное поручение',
  waybill: 'ТОРГ-12',
  upd: 'УПД',
}

export const EDGE_CASE_META = {
  ip_forms: {
    label: 'ИП-формы',
    icon: 'mdi-account-tie-outline',
    hint: 'Часть сторон становятся индивидуальными предпринимателями (12-значный ИНН, без КПП). Режим интенсивности задаётся ниже.',
  },
  missing_optional: {
    label: 'Пропуски полей',
    icon: 'mdi-eye-off-outline',
    hint: 'У юр.лиц могут отсутствовать КПП и/или город — как на сжатых бланках. Интенсивность задаётся ниже.',
  },
  multiline_names: {
    label: 'Перенос имени',
    icon: 'mdi-format-text-wrapping-wrap',
    hint: 'У части юр.лиц длинное дефисное имя разрывается переносом строки («ООО «Альфа-Бета-↵Гамма-Дельта»»).',
  },
  reordered_blocks: {
    label: 'Перестановка сторон',
    icon: 'mdi-swap-vertical',
    hint: 'Стороны рендерятся в обратном порядке (Покупатель раньше Продавца).',
  },
}

export const IP_MODE_META = {
  random: {
    label: 'Случайно',
    hint: '~35% сторон становятся ИП.',
  },
  guaranteed: {
    label: 'Гарантированно ≥1',
    hint: 'Хотя бы одна сторона — ИП, остальные — случайно ~35%.',
  },
  all: {
    label: 'Все ИП',
    hint: 'Все стороны документа — ИП.',
  },
}

export const MISSING_MODE_META = {
  random: {
    label: 'Случайно',
    hint: '~20% юр.лиц без КПП и ~15% без города.',
  },
  guaranteed: {
    label: 'Гарантированно ≥1',
    hint: 'Минимум один юр.лицо без КПП и без города; остальные — случайно.',
  },
  all: {
    label: 'Все ЛЕ',
    hint: 'Все юр.лица без КПП и без города (стресс-тест разреженных бланков).',
  },
}

export function edgeCaseLabel(id) { return EDGE_CASE_META[id]?.label || id }
export function edgeCaseHint(id) { return EDGE_CASE_META[id]?.hint || '' }
export function edgeCaseIcon(id) { return EDGE_CASE_META[id]?.icon || 'mdi-flask-outline' }
export function ipModeLabel(id) { return IP_MODE_META[id]?.label || id }
export function ipModeHint(id) { return IP_MODE_META[id]?.hint || '' }
export function missingModeLabel(id) { return MISSING_MODE_META[id]?.label || id }
export function missingModeHint(id) { return MISSING_MODE_META[id]?.hint || '' }

export const JUNK_KIND_META = {
  'junk-text': {
    label: 'Нерелевантный текст',
    ext: '.txt',
    icon: 'mdi-text-box-outline',
    hint: 'Корректный текст без бизнес-смысла: лекция, поздравительная открытка, заметка. Система должна определить, что это не документ, и пометить файл как «неизвестный тип».',
  },
  'junk-empty': {
    label: 'Пустой файл',
    ext: '.txt',
    icon: 'mdi-file-question-outline',
    hint: 'Файл нулевого размера. Отклоняется ещё на этапе загрузки, до попадания в обработку.',
  },
  'junk-garbled': {
    label: 'Битый PDF',
    ext: '.pdf',
    icon: 'mdi-file-cancel-outline',
    hint: 'Файл выглядит как PDF (правильный заголовок), но внутри произвольные байты. Парсер либо отклоняет файл, либо возвращает пустой текст — документ помечается как «с предупреждением».',
  },
  'junk-wrong-ext': {
    label: 'Неверное расширение',
    ext: '.docx',
    icon: 'mdi-file-alert-outline',
    hint: 'Обычный текст, сохранённый с расширением `.docx`. Парсер обнаруживает расхождение содержимого и расширения и сообщает об ошибке.',
  },
}

export function junkKindLabel(id) { return JUNK_KIND_META[id]?.label || id }
export function junkKindHint(id)  { return JUNK_KIND_META[id]?.hint  || '' }
export function junkKindIcon(id)  { return JUNK_KIND_META[id]?.icon  || 'mdi-help-circle-outline' }

export const TECH_STACK = [
  { component: 'Веб-интерфейс', icon: 'mdi-vuejs', tone: 'primary',
    tech: 'Vue 3 + Vuetify 3 + Pinia + Vite',
    detail: 'SPA, отдаётся через nginx 1.27' },
  { component: 'API', icon: 'mdi-api', tone: 'info',
    tech: 'FastAPI 0.115 + asyncpg',
    detail: 'Python 3.12, JWT-аутентификация (HS256), bcrypt' },
  { component: 'Загрузка', icon: 'mdi-cloud-upload-outline', tone: 'info',
    tech: 'FastAPI + pdfplumber, python-docx, openpyxl, pandas',
    detail: 'python-magic для определения MIME, sha256 для дедупликации' },
  { component: 'Очередь сообщений', icon: 'mdi-pipe', tone: 'warning',
    tech: 'Apache Kafka 7.5 + Zookeeper',
    detail: 'topic raw-docs, manual offset commit после успешной записи' },
  { component: 'Обработка', icon: 'mdi-cog-transfer-outline', tone: 'warning',
    tech: 'aiokafka consumer + regex',
    detail: 'consumer group transform-mvp, идемпотентный UPSERT по doc_id' },
  { component: 'База данных', icon: 'mdi-database', tone: 'success',
    tech: 'PostgreSQL 16',
    detail: 'tsvector + GIN для полнотекстового поиска, JSONB для гибких полей' },
  { component: 'Файловое хранилище', icon: 'mdi-folder-multiple-outline', tone: 'success',
    tech: 'Docker named volume',
    detail: 'ключ — sha256 файла, повторная загрузка переиспользует существующий' },
  { component: 'Метрики', icon: 'mdi-chart-bell-curve-cumulative', tone: 'secondary',
    tech: 'Prometheus 2.50 + kafka-exporter',
    detail: 'scrape interval 15s, custom counters в extract / transform' },
  { component: 'Логи', icon: 'mdi-text-search', tone: 'secondary',
    tech: 'Loki 3.3 + Promtail 3.3',
    detail: 'filesystem retention 7 дней, docker_sd_configs автоопределяет контейнеры' },
  { component: 'Дашборды', icon: 'mdi-monitor-dashboard', tone: 'secondary',
    tech: 'Grafana 10.4',
    detail: 'provisioned datasources + дашборды, Explore для логов и метрик' },
  { component: 'Деплой', icon: 'mdi-docker', tone: 'secondary',
    tech: 'Docker Compose',
    detail: '8 контейнеров, всё локально на macOS / Linux' },
]

export const PIPELINE_STAGES = [
  // Нормальный путь: документ последовательно проходит эти стадии и попадает в БД.
  { id: 'uploaded',              icon: 'mdi-tray-arrow-up',          color: 'info',    phase: 'flow',
    title: 'Загружен',           desc: 'Файл сохранён, ему присвоен идентификатор. Ещё не пошёл в обработку.' },
  { id: 'extracted',             icon: 'mdi-text-box-outline',       color: 'info',    phase: 'flow',
    title: 'Прочитан',           desc: 'Из файла извлечён текст. Документ передан на анализ.' },
  { id: 'classified',            icon: 'mdi-shape-outline',          color: 'info',    phase: 'flow',
    title: 'Классифицирован',    desc: 'Определён вид документа: счёт-фактура, акт, договор и т.п.' },
  { id: 'validated',             icon: 'mdi-check-circle-outline',   color: 'success', phase: 'flow',
    title: 'Валидирован',        desc: 'Все ключевые поля извлечены и прошли проверку без ошибок.' },
  { id: 'loaded',                icon: 'mdi-database-check-outline', color: 'success', phase: 'flow',
    title: 'В БД',               desc: 'Документ полностью обработан и доступен для поиска и просмотра.' },
  // Альтернативные финалы — достигаются вместо «В БД», когда что-то пошло не так.
  { id: 'validated_with_errors', icon: 'mdi-alert-outline',          color: 'warning', phase: 'alt',
    title: 'С предупреждением',  desc: 'Документ обработан, но с замечаниями: вид не удалось определить, ИНН не прошёл проверку, дата вне допустимого диапазона. Документ всё равно сохраняется и доступен для просмотра.' },
  { id: 'failed',                icon: 'mdi-close-circle-outline',   color: 'error',   phase: 'alt',
    title: 'Ошибка',             desc: 'Внутренняя ошибка на любой из стадий: сбой парсера, недоступность базы, неожиданное исключение. Подробности доступны в журнале событий документа.' },
]

export function formatDocType(value) {
  if (!value) return '—'
  return DOC_TYPE_LABELS[value] || value
}

export function docTypeOptions(values) {
  return values.map((v) => ({ value: v, title: formatDocType(v) }))
}

export const STATUS_META = {
  uploaded: { label: 'Загружен', color: 'info', icon: 'mdi-tray-arrow-up' },
  extracted: { label: 'Прочитан', color: 'info', icon: 'mdi-text-box-outline' },
  classified: { label: 'Классифицирован', color: 'info', icon: 'mdi-shape-outline' },
  validated: { label: 'Валидирован', color: 'success', icon: 'mdi-check-circle-outline' },
  validated_with_errors: { label: 'С предупреждением', color: 'warning', icon: 'mdi-alert-outline' },
  loaded: { label: 'В БД', color: 'success', icon: 'mdi-database-check-outline' },
  failed: { label: 'Ошибка', color: 'error', icon: 'mdi-close-circle-outline' },
}

export function statusLabel(s) { return STATUS_META[s]?.label || s || '—' }
export function statusColor(s) { return STATUS_META[s]?.color || 'default' }
export function statusIcon(s) { return STATUS_META[s]?.icon || 'mdi-help-circle-outline' }

const amountFormat = new Intl.NumberFormat('ru-RU', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

export function formatAmount(value, currency) {
  if (value == null || value === '') return ''
  const n = Number(value)
  if (isNaN(n)) return String(value)
  return amountFormat.format(n) + ' ' + (currency || 'RUB')
}

export function uploadRowVisual(r) {
  if (r.deduplicated) return { icon: 'mdi-equal', color: 'info' }
  if (r.final_status === 'loaded') return { icon: 'mdi-check-circle', color: 'success' }
  if (r.final_status === 'validated_with_errors') return { icon: 'mdi-alert-outline', color: 'warning' }
  if (r.final_status === 'failed') return { icon: 'mdi-close-circle', color: 'error' }
  if (r.http_status >= 400 || (r.http_status === 0 && r.error)) {
    return { icon: 'mdi-alert-circle', color: 'error' }
  }
  return { icon: 'mdi-progress-clock', color: 'medium-emphasis' }
}

export function uploadRowLabel(r) {
  if (r.deduplicated) return 'Дубль'
  if (r.final_status === 'loaded') return 'В БД'
  if (r.final_status === 'validated_with_errors') return 'С предупреждением'
  if (r.final_status === 'failed') return 'Ошибка пайплайна'
  if (r.http_status >= 400) return `Отклонён при загрузке (HTTP ${r.http_status})`
  if (r.http_status === 0 && r.error) return 'Сетевая ошибка'
  return 'Ещё обрабатывается…'
}

export const FILE_ICON_META = {
  pdf:  { icon: 'mdi-file-pdf-box',         color: '#EF4444' },
  docx: { icon: 'mdi-file-word-box',        color: '#2563EB' },
  doc:  { icon: 'mdi-file-word-box',        color: '#2563EB' },
  xlsx: { icon: 'mdi-file-excel-box',       color: '#10B981' },
  xls:  { icon: 'mdi-file-excel-box',       color: '#10B981' },
  csv:  { icon: 'mdi-file-delimited-outline', color: '#0EA5E9' },
  txt:  { icon: 'mdi-text-box-outline',     color: '#94A3B8' },
}

function fileExt(name) {
  if (!name) return ''
  const i = name.lastIndexOf('.')
  return i === -1 ? '' : name.slice(i + 1).toLowerCase()
}

export function fileIcon(name) {
  return FILE_ICON_META[fileExt(name)]?.icon || 'mdi-file-outline'
}

export function fileIconColor(name) {
  return FILE_ICON_META[fileExt(name)]?.color || '#94A3B8'
}

export function formatBytes(bytes) {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} Б`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} КБ`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} МБ`
  return `${(bytes / 1024 ** 3).toFixed(2)} ГБ`
}
