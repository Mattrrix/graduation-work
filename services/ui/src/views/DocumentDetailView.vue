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
} from '../utils/format.js'

const props = defineProps({ id: String })
const router = useRouter()

const doc = ref(null)
const audit = ref([])
const loading = ref(false)
const deleting = ref(false)
const downloading = ref(false)
const confirmDelete = ref(false)
const tab = ref('text')

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

const infoRows = computed(() => {
  if (!doc.value) return []
  const d = doc.value
  return [
    { label: 'Тип', value: formatDocType(d.doc_type), errorKey: 'document' },
    { label: 'Номер', value: d.number || '—', errorKey: 'number' },
    { label: 'Дата документа', value: d.doc_date || '—', errorKey: 'date' },
    { label: 'Контрагент', value: d.counterparty_name || '—', errorKey: 'counterparty_name' },
    { label: 'ИНН', value: d.counterparty_inn || '—', mono: true, errorKey: 'inn' },
    { label: 'КПП', value: d.counterparty_kpp || '—', mono: true, errorKey: 'kpp' },
    { label: 'Сумма', value: d.amount_total ? formatAmount(d.amount_total, d.currency) : '—', errorKey: 'amount_total' },
  ]
})

const ERROR_MESSAGES = {
  unknown_document_type: 'Тип документа не распознан — нет регулярных выражений, совпавших с содержимым',
  checksum: 'Не прошёл проверку контрольной суммы',
  out_of_range: 'Значение вне допустимого диапазона (даты: 2000–2030)',
  non_positive: 'Должно быть положительным числом',
  missing: 'Поле не извлечено — без распознанного типа документа regex-правила не запускались',
}

const FIELD_LABELS = {
  document: 'Тип документа',
  inn: 'ИНН',
  date: 'Дата',
  amount_total: 'Сумма',
  number: 'Номер',
  counterparty_name: 'Контрагент',
  kpp: 'КПП',
}

function errorMessage(err) {
  return ERROR_MESSAGES[err.code] || err.code
}

function errorFieldLabel(err) {
  return FIELD_LABELS[err.field] || err.field
}

const PRIMARY_FIELDS = [
  { key: 'number', getter: (d) => d.number },
  { key: 'date', getter: (d) => d.doc_date },
  { key: 'counterparty_name', getter: (d) => d.counterparty_name },
  { key: 'inn', getter: (d) => d.counterparty_inn },
  { key: 'kpp', getter: (d) => d.counterparty_kpp },
  { key: 'amount_total', getter: (d) => d.amount_total },
]

const docErrors = computed(() => doc.value?.fields?.errors || [])
const hasUnknownType = computed(() =>
  docErrors.value.some((e) => e.code === 'unknown_document_type'),
)

const docWarnings = computed(() => {
  if (!doc.value || !hasUnknownType.value) return []
  const warnings = []
  for (const f of PRIMARY_FIELDS) {
    if (!f.getter(doc.value)) {
      warnings.push({ field: f.key, code: 'missing', value: null })
    }
  }
  return warnings
})

const errorByField = computed(() => {
  const map = {}
  for (const e of docErrors.value) map[e.field] = e
  return map
})

const warningByField = computed(() => {
  const map = {}
  for (const w of docWarnings.value) map[w.field] = w
  return map
})

const allIssues = computed(() => [...docErrors.value, ...docWarnings.value])
const hasIssues = computed(() => allIssues.value.length > 0)
const hasErrors = computed(() => docErrors.value.length > 0)

function issueColor(iss) {
  return iss.code === 'missing' ? 'warning' : 'error'
}

function issueIcon(iss) {
  return iss.code === 'missing' ? 'mdi-alert-outline' : 'mdi-alert-circle'
}

function rowIssue(errorKey) {
  if (!errorKey) return null
  return errorByField.value[errorKey] || warningByField.value[errorKey] || null
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
  transform: 'Извлечение полей',
  classify: 'Классификация',
  ner: 'Распознавание полей',
  validate: 'Валидация',
  normalize: 'Нормализация',
  load: 'Запись в БД',
}

function stageLabel(stage) {
  return STAGE_LABELS[stage] || stage
}

function eventDot(status) {
  if (status === 'ok') return 'success'
  if (status === 'warning') return 'warning'
  return 'error'
}

function parseEventChips(ev) {
  const chips = []
  const msg = ev.message || ''
  const m = msg.match(/doc_type=(\w+),\s*errors=(\d+),\s*dup=(\w+)/)
  if (m) {
    const [, , errors, dup] = m
    if (parseInt(errors) === 0) {
      chips.push({ label: 'Без ошибок', color: 'success', icon: 'mdi-check-circle-outline' })
    } else {
      chips.push({ label: `Ошибок: ${errors}`, color: 'warning', icon: 'mdi-alert-outline' })
    }
    if (!dup || dup === 'None' || dup === 'null') {
      chips.push({ label: 'Не дубликат', color: 'info', icon: 'mdi-shield-check-outline' })
    } else {
      chips.push({ label: 'Дубликат', color: 'warning', icon: 'mdi-content-duplicate' })
    }
  }
  return chips
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
      v-else-if="hasIssues"
      type="warning"
      variant="tonal"
      class="mb-4"
      border="start"
    >
      <div style="font-weight:600;margin-bottom:6px">Документ обработан с предупреждениями</div>
      <ul style="margin:0;padding-left:0;list-style:none;font-size:13.5px">
        <li
          v-for="(iss, i) in allIssues"
          :key="i"
          style="margin-top:4px;display:flex;align-items:start;gap:8px"
        >
          <v-icon :icon="issueIcon(iss)" :color="issueColor(iss)" size="16" style="margin-top:2px;flex-shrink:0" />
          <div>
            <strong>{{ errorFieldLabel(iss) }}:</strong>
            {{ errorMessage(iss) }}
            <span v-if="iss.value" class="text-medium-emphasis">— «{{ iss.value }}»</span>
          </div>
        </li>
      </ul>
    </v-alert>

    <v-row>
      <v-col cols="12" md="7">
        <v-card class="app-card">
          <v-card-text class="pa-5">
            <div class="d-flex align-center mb-3" style="gap:8px">
              <span class="text-subtitle-2" style="font-weight:600">Сведения</span>
              <v-tooltip v-if="hasIssues" location="top">
                <template #activator="{ props }">
                  <v-icon
                    v-bind="props"
                    size="18"
                    :color="hasErrors ? 'error' : 'warning'"
                  >
                    {{ hasErrors ? 'mdi-alert-circle' : 'mdi-alert-outline' }}
                  </v-icon>
                </template>
                {{ allIssues.length }} проблем(ы) — детали выше и в строках полей
              </v-tooltip>
            </div>
            <div>
              <div v-for="row in infoRows" :key="row.label" class="info-row">
                <div class="info-row-label d-flex align-center" style="gap:6px">
                  <span>{{ row.label }}</span>
                  <v-tooltip v-if="rowIssue(row.errorKey)" location="top">
                    <template #activator="{ props }">
                      <v-icon
                        v-bind="props"
                        size="14"
                        :color="issueColor(rowIssue(row.errorKey))"
                      >
                        {{ issueIcon(rowIssue(row.errorKey)) }}
                      </v-icon>
                    </template>
                    {{ errorMessage(rowIssue(row.errorKey)) }}
                  </v-tooltip>
                </div>
                <div
                  class="info-row-value"
                  :class="{
                    mono: row.mono && row.value !== '—',
                    'text-error': errorByField[row.errorKey],
                    'text-warning': !errorByField[row.errorKey] && warningByField[row.errorKey],
                  }"
                >
                  {{ row.value }}
                </div>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="5">
        <v-card class="app-card">
          <v-card-text class="pa-5">
            <div class="text-subtitle-2 mb-4" style="font-weight:600">Аудит-трейл</div>
            <v-timeline density="compact" side="end" align="start" truncate-line="both">
              <v-timeline-item
                v-for="ev in audit"
                :key="ev.id"
                :dot-color="eventDot(ev.status)"
                size="x-small"
              >
                <div class="d-flex align-center" style="gap:8px;flex-wrap:wrap">
                  <span class="text-body-2" style="font-weight:600">{{ stageLabel(ev.stage) }}</span>
                  <v-chip
                    v-if="ev.status !== 'ok'"
                    size="x-small"
                    variant="tonal"
                    :color="eventDot(ev.status)"
                  >
                    {{ ev.status }}
                  </v-chip>
                </div>
                <div class="text-caption text-medium-emphasis mt-1">{{ formatDateTime(ev.created_at) }}</div>
                <div
                  v-if="parseEventChips(ev).length"
                  class="d-flex mt-2"
                  style="gap:6px;flex-wrap:wrap"
                >
                  <v-chip
                    v-for="(c, i) in parseEventChips(ev)"
                    :key="i"
                    size="x-small"
                    variant="tonal"
                    :color="c.color"
                    :prepend-icon="c.icon"
                  >
                    {{ c.label }}
                  </v-chip>
                </div>
              </v-timeline-item>
            </v-timeline>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-card class="app-card mt-4">
      <v-tabs v-model="tab" color="primary" align-tabs="start" density="comfortable">
        <v-tab value="text" prepend-icon="mdi-text-box-outline">Извлечённый текст</v-tab>
        <v-tab value="fields" prepend-icon="mdi-code-json">Извлечённые поля</v-tab>
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
