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

export const DATE_ROLE_LABELS = {
  doc_date: 'Дата документа',
  due_date: 'Срок оплаты',
  delivery_date: 'Дата поставки',
}

export const AMOUNT_ROLE_LABELS = {
  total: 'С НДС',
  vat: 'НДС',
}

export function dateRoleLabel(role) {
  return DATE_ROLE_LABELS[role] || role || 'Без роли'
}

export function amountRoleLabel(role) {
  return AMOUNT_ROLE_LABELS[role] || role || 'Без роли'
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
    tech: 'aiokafka consumer + regex + языковая модель',
    detail: 'consumer group transform-mvp, идемпотентный UPSERT по doc_id' },
  { component: 'Языковая модель (основная)', icon: 'mdi-brain', tone: 'warning',
    tech: 'Qwen3.5-9B-MLX-4bit · mlx-lm',
    detail: 'нативно на хосте через mlx_lm.server :8112, классификация + извлечение полей одним запросом' },
  { component: 'Языковая модель (альтернатива)', icon: 'mdi-cloud-outline', tone: 'warning',
    tech: 'Sber GigaChat (Lite / Pro / Max)',
    detail: 'облачный бэкенд, переключается одной env-переменной LLM_BACKEND' },
  { component: 'OCR (распознавание сканов)', icon: 'mdi-image-text', tone: 'warning',
    tech: 'PaddleOCR-VL 1.5 · mlx-vlm-server',
    detail: 'нативно на хосте :8111, текст + таблицы + layout одной моделью' },
  { component: 'База данных', icon: 'mdi-database', tone: 'success',
    tech: 'PostgreSQL 16',
    detail: 'tsvector + GIN для полнотекстового поиска, JSONB для гибких полей' },
  { component: 'Файловое хранилище', icon: 'mdi-folder-multiple-outline', tone: 'success',
    tech: 'Docker named volume',
    detail: 'ключ — sha256 файла, повторная загрузка переиспользует существующий' },
  { component: 'Сессии и авторизация', icon: 'mdi-shield-key-outline', tone: 'success',
    tech: 'Redis 7.4',
    detail: 'refresh-токены (30 дней) + denylist отозванных access-JWT, AOF-persistence' },
  { component: 'Метрики', icon: 'mdi-chart-bell-curve-cumulative', tone: 'secondary',
    tech: 'Prometheus 2.50 + kafka-exporter + redis-exporter',
    detail: 'scrape interval 15s, custom counters в extract / transform' },
  { component: 'Системные метрики', icon: 'mdi-server-network', tone: 'secondary',
    tech: 'cAdvisor 0.47',
    detail: 'CPU / RAM / диск по контейнерам и по пайплайну в целом' },
  { component: 'Логи', icon: 'mdi-text-search', tone: 'secondary',
    tech: 'Loki 3.3 + Promtail 3.3',
    detail: 'filesystem retention 7 дней, docker_sd_configs автоопределяет контейнеры' },
  { component: 'Дашборды', icon: 'mdi-monitor-dashboard', tone: 'secondary',
    tech: 'Grafana 10.4',
    detail: 'provisioned datasources + дашборды, Explore для логов и метрик' },
  { component: 'Деплой', icon: 'mdi-docker', tone: 'secondary',
    tech: 'Docker Compose',
    detail: '15 контейнеров; AI-сервисы (Qwen, PaddleOCR) запускаются нативно на хосте' },
]

export const PIPELINE_STAGES = [
  { id: 'uploaded',              icon: 'mdi-tray-arrow-up',          color: 'info',    phase: 'flow',
    title: 'Загружен',           desc: 'Файл сохранён, ему присвоен идентификатор. Ещё не пошёл в обработку.' },
  { id: 'extracted',             icon: 'mdi-text-box-outline',       color: 'info',    phase: 'flow',
    title: 'Обрабатывается',     desc: 'Из файла извлечён текст, документ в Kafka. Дальше: regex-кандидаты (мс) → LLM-извлечение полей и классификация (~16 с) → сверка с regex и валидация (мс) → запись в БД.' },
  { id: 'loaded',                icon: 'mdi-database-check-outline', color: 'success', phase: 'flow',
    title: 'В БД',               desc: 'Документ полностью обработан и доступен для поиска, просмотра и редактирования через HITL-форму.' },
  { id: 'validated_with_errors', icon: 'mdi-alert-outline',          color: 'warning', phase: 'alt',
    title: 'С предупреждением',  desc: 'Документ обработан, но с замечаниями: тип не определён, ИНН не прошёл проверку, дата вне допустимого диапазона. Документ всё равно сохраняется и доступен для просмотра/правки. Кнопка «Перепроцессить» возвращает его в обработку.' },
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
  uploaded: { label: 'Обрабатывается', color: 'info', icon: 'mdi-cog-sync-outline' },
  extracted: { label: 'Обрабатывается', color: 'info', icon: 'mdi-cog-sync-outline' },
  classified: { label: 'Обрабатывается', color: 'info', icon: 'mdi-cog-sync-outline' },
  validated: { label: 'Обрабатывается', color: 'info', icon: 'mdi-cog-sync-outline' },
  validated_with_errors: { label: 'С предупреждением', color: 'warning', icon: 'mdi-alert-outline' },
  loaded: { label: 'В БД', color: 'success', icon: 'mdi-database-check-outline' },
  failed: { label: 'Ошибка', color: 'error', icon: 'mdi-close-circle-outline' },
}

export function statusLabel(s) { return STATUS_META[s]?.label || s || '—' }
export function statusColor(s) { return STATUS_META[s]?.color || 'default' }
export function statusIcon(s) { return STATUS_META[s]?.icon || 'mdi-help-circle-outline' }

const TERMINAL_STATUSES = new Set(['loaded', 'validated_with_errors', 'failed'])

export function rowStatusDisplay(item) {
  const s = item?.status
  if (TERMINAL_STATUSES.has(s)) {
    return { label: statusLabel(s), color: statusColor(s), icon: statusIcon(s) }
  }
  const stage = item?.last_stage
  let label
  if (stage === 'ocr') label = 'Распознавание скана'
  else if (stage === 'candidates') label = 'Извлечение полей (LLM)'
  else if (stage === 'llm' || stage === 'classify' || stage === 'reconcile' || stage === 'validate') label = 'Сохранение'
  else label = 'В очереди на LLM'
  return { label, color: 'info', icon: 'mdi-cog-sync-outline' }
}

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
  if (r.cancelled) return { icon: 'mdi-cancel', color: 'medium-emphasis' }
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
  if (r.cancelled) return 'Отменено'
  if (r.deduplicated) return 'Дубль'
  if (r.final_status === 'loaded') return 'В БД'
  if (r.final_status === 'validated_with_errors') return 'С предупреждением'
  if (r.final_status === 'failed') return 'Ошибка пайплайна'
  if (r.http_status >= 400) return `Отклонён при загрузке (HTTP ${r.http_status})`
  if (r.http_status === 0 && r.error) return 'Сетевая ошибка'
  return 'Ещё обрабатывается…'
}

export function uploadRowStageLabel(r) {
  const stages = r.stages_seen || []
  const has = (s) => stages.includes(s)
  if (has('load')) return null
  if (has('llm')) return 'Сохранение'
  if (has('candidates')) return 'Извлечение полей (LLM)'
  if (has('extract')) return 'В очереди на LLM'
  if (has('ocr')) return 'Распознавание скана'
  return 'Чтение файла'
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
