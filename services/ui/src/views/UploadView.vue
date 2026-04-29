<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import client from '../api/client.js'
import { formatBytes, statusLabel, statusColor, uploadRowVisual, uploadRowLabel, uploadRowStageLabel } from '../utils/format.js'

const queue = ref([])
const results = ref([])
const uploading = ref(false)
const waitingPipeline = ref(false)
const dragActive = ref(false)
const fileInput = ref(null)
const dirInput = ref(null)

const TERMINAL_STATUSES = new Set(['loaded', 'validated_with_errors', 'failed'])

const VISIBLE_STAGES = [
  { key: 'extract', label: 'Чтение файла' },
  { key: 'llm', label: 'Извлечение полей (LLM)' },
  { key: 'load', label: 'Сохранение' },
]
const STAGE_CURRENT_PHASE = {
  ocr: 0,
  extract: 1, candidates: 1,
  llm: 2,
  classify: 2, reconcile: 2, validate: 2,
  load: 3,
}

function stageLabel(stage) {
  const p = STAGE_CURRENT_PHASE[stage]
  if (p === undefined) return stage
  const idx = Math.min(p, VISIBLE_STAGES.length - 1)
  return VISIBLE_STAGES[idx].label
}

function stageProgress(r) {
  const stages = r.stages_seen || []
  if (!stages.length) return 0
  let cur = 0
  for (const s of stages) {
    const p = STAGE_CURRENT_PHASE[s]
    if (p !== undefined && p > cur) cur = p
  }
  return cur
}

const totalSize = computed(() => queue.value.reduce((s, f) => s + f.size, 0))
const loadedCount = computed(() => results.value.filter((r) => r.ok && !r.deduplicated && r.final_status === 'loaded').length)
const warningCount = computed(() => results.value.filter((r) => r.ok && !r.deduplicated && r.final_status === 'validated_with_errors').length)
const pipelineFailedCount = computed(() => results.value.filter((r) => r.ok && !r.deduplicated && r.final_status === 'failed').length)
const dupCount = computed(() => results.value.filter((r) => r.ok && r.deduplicated).length)
const rejectedCount = computed(() => results.value.filter((r) => !r.ok && !r.pending).length)

function isHiddenSystemFile(name) {
  if (!name) return false
  const base = String(name).split('/').pop() || ''
  // Системные мусорные файлы, которые macOS/Windows кладут в каталог при drag-n-drop папки.
  return base.startsWith('.') || base === 'Thumbs.db' || base === 'desktop.ini'
}

function addFiles(files) {
  for (const f of files) {
    if (isHiddenSystemFile(f.webkitRelativePath || f.name)) continue
    queue.value.push(f)
  }
}

function onFileChange(e) {
  addFiles(e.target.files)
  e.target.value = ''
}

async function readEntryRecursive(entry) {
  if (entry.isFile) {
    return new Promise((resolve, reject) => entry.file((f) => resolve([f]), reject))
  }
  const reader = entry.createReader()
  const collected = []
  while (true) {
    const batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject))
    if (!batch.length) break
    for (const child of batch) {
      const files = await readEntryRecursive(child)
      collected.push(...files)
    }
  }
  return collected
}

async function onDrop(e) {
  dragActive.value = false
  const items = e.dataTransfer.items
  if (items && items.length && items[0].webkitGetAsEntry) {
    for (const item of items) {
      const entry = item.webkitGetAsEntry()
      if (entry) addFiles(await readEntryRecursive(entry))
    }
  } else {
    addFiles(e.dataTransfer.files)
  }
}

function removeFromQueue(idx) {
  queue.value.splice(idx, 1)
}

function clearQueue() {
  queue.value = []
  cancelAll()
  results.value = []
  saveResults()
}

const STORAGE_KEY = 'upload_results_v2'
let restoring = false

function persistableResults() {
  return results.value.map((r) => {
    const { _abort, ...rest } = r
    return rest
  })
}

let saveTimer = null
function saveResults() {
  if (restoring) return
  if (saveTimer) return
  saveTimer = setTimeout(() => {
    saveTimer = null
    try {
      if (results.value.length) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(persistableResults()))
      } else {
        localStorage.removeItem(STORAGE_KEY)
      }
    } catch {}
  }, 400)
}

function restoreResults() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || !parsed.length) return
    restoring = true
    results.value = parsed
      .filter((r) => r.doc_id || r.error || r.cancelled || (r.http_status && r.http_status >= 400))
      .map((r) => ({ ...r, _abort: null }))
    restoring = false
  } catch {
    restoring = false
  }
}

watch(results, saveResults, { deep: true })

const uploadAborters = new Set()

function cancelAllUploads() {
  for (const c of uploadAborters) {
    try { c.abort() } catch {}
  }
  uploadAborters.clear()
}

async function deleteDocSilently(docId) {
  if (!docId) return
  try { await client.delete(`/documents/${docId}`) } catch {}
}

async function cancelAllInflight() {
  const ids = []
  for (const r of results.value) {
    if (r.ok && r.doc_id && !TERMINAL_STATUSES.has(r.final_status || '')) {
      r.cancelled = true
      ids.push(r.doc_id)
    }
  }
  if (ids.length) {
    try { await client.post('/documents/bulk-delete', { doc_ids: ids }) } catch {}
  }
}

function cancelAll() {
  cancelAllUploads()
  if (pollAbort) pollAbort.stopped = true
  cancelAllInflight()
}

async function dismissRow(idx) {
  const r = results.value[idx]
  if (r?._abort) {
    try { r._abort.abort() } catch {}
  }
  const inflightId =
    r?.ok && r?.doc_id && !TERMINAL_STATUSES.has(r.final_status || '') ? r.doc_id : null
  results.value.splice(idx, 1)
  if (inflightId) deleteDocSilently(inflightId)
}

async function upload() {
  uploading.value = true
  results.value = []
  saveResults()

  for (const f of queue.value) {
    const fd = new FormData()
    fd.append('file', f)
    const ctrl = new AbortController()
    uploadAborters.add(ctrl)
    results.value.push({
      name: f.webkitRelativePath || f.name,
      ok: false,
      pending: true,
      http_status: 0,
      _abort: ctrl,
    })
    // Мутировать строку только через results.value[idx]: локальная ссылка минует Vue-прокси.
    const idx = results.value.length - 1
    try {
      const { data } = await client.post('/documents', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        signal: ctrl.signal,
      })
      Object.assign(results.value[idx], { ok: true, pending: false, final_status: null, ...data, _abort: null })
    } catch (e) {
      if (ctrl.signal.aborted) {
        Object.assign(results.value[idx], { ok: false, pending: false, http_status: 0, error: 'Загрузка отменена', cancelled: true, _abort: null })
      } else {
        Object.assign(results.value[idx], {
          ok: false,
          pending: false,
          http_status: e.response?.status || 0,
          error: e.response?.data?.detail || e.message,
          _abort: null,
        })
      }
    } finally {
      uploadAborters.delete(ctrl)
    }
  }

  uploading.value = false
  queue.value = []

  const inProgress = results.value.filter((r) => r.ok && !r.deduplicated && r.doc_id && !r.cancelled)
  if (inProgress.length) {
    waitingPipeline.value = true
    try {
      await pollUntilDone(90000)
    } finally {
      waitingPipeline.value = false
    }
  }
}

let pollAbort = null

async function pollUntilDone(timeoutMs) {
  const deadline = Date.now() + timeoutMs
  pollAbort = { stopped: false }
  while (Date.now() < deadline && !pollAbort.stopped) {
    const pending = results.value.filter(
      (r) => r.ok && r.doc_id && !r.cancelled && !TERMINAL_STATUSES.has(r.final_status || ''),
    )
    if (!pending.length) break
    await refreshBatch(pending.map((r) => r.doc_id))
    await new Promise((res) => setTimeout(res, 600))
  }
  pollAbort = null
}

async function refreshBatch(docIds) {
  if (!docIds.length) return
  try {
    const { data } = await client.post('/documents/statuses', { doc_ids: docIds })
    const map = data.items || {}
    for (const r of results.value) {
      if (!r.doc_id) continue
      const info = map[r.doc_id]
      if (!info) continue
      r.final_status = info.status
      r.stages_seen = info.stages || []
      r.current_stage = info.last?.stage || null
      r.current_message = info.last?.message || ''
      r.current_status = info.last?.status || 'ok'
    }
  } catch {}
}

function clearResults() {
  cancelAll()
  results.value = []
  saveResults()
}

onMounted(() => {
  restoreResults()
  const inflight = results.value.filter(
    (r) => r.ok && r.doc_id && !r.cancelled && !TERMINAL_STATUSES.has(r.final_status || ''),
  )
  if (inflight.length) {
    waitingPipeline.value = true
    pollUntilDone(120000).finally(() => { waitingPipeline.value = false })
  }
})

onBeforeUnmount(() => {
  if (pollAbort) pollAbort.stopped = true
})

const rowVisual = uploadRowVisual
const rowLabel = uploadRowLabel
const rowStageLabel = uploadRowStageLabel

function isInflight(r) {
  return r.ok && !r.deduplicated && r.doc_id && !r.cancelled && !TERMINAL_STATUSES.has(r.final_status || '')
}
</script>

<template>
  <div>
    <div class="page-header">
      <h1 class="page-title">Загрузка документов</h1>
      <p class="page-subtitle">Перетащите файлы или папку — поддерживаются PDF, DOCX, XLSX, CSV, TXT</p>
    </div>

    <v-card class="app-card">
      <v-card-text class="pa-5">
        <div
          class="drop-zone"
          :class="{ active: dragActive }"
          @dragover.prevent="dragActive = true"
          @dragenter.prevent="dragActive = true"
          @dragleave.prevent="dragActive = false"
          @drop.prevent="onDrop"
        >
          <div class="drop-zone-icon">
            <v-icon size="36">mdi-cloud-upload-outline</v-icon>
          </div>
          <div class="text-h6" style="font-weight:600">Перетащите файлы или папку сюда</div>
          <div class="text-body-2 text-medium-emphasis mt-1">PDF · DOCX · XLSX · CSV · TXT · до сотен файлов одновременно</div>
          <div class="mt-5 d-flex justify-center" style="gap:10px;flex-wrap:wrap">
            <v-btn variant="tonal" color="primary" prepend-icon="mdi-paperclip" @click="fileInput.click()">
              Выбрать файлы
            </v-btn>
            <v-btn variant="tonal" prepend-icon="mdi-folder-multiple-outline" @click="dirInput.click()">
              Выбрать папку
            </v-btn>
          </div>
          <input ref="fileInput" type="file" multiple style="display:none" @change="onFileChange" />
          <input ref="dirInput" type="file" webkitdirectory directory multiple style="display:none" @change="onFileChange" />
        </div>

        <div v-if="queue.length" class="mt-5 d-flex align-center" style="gap:12px">
          <div>
            <div class="text-subtitle-2" style="font-weight:600">В очереди: {{ queue.length }} файла(ов)</div>
            <div class="text-caption text-medium-emphasis">{{ formatBytes(totalSize) }} суммарно</div>
          </div>
          <v-spacer />
          <v-btn variant="text" size="small" @click="clearQueue">Очистить</v-btn>
          <v-btn
            color="primary"
            size="default"
            :loading="uploading"
            prepend-icon="mdi-rocket-launch-outline"
            @click="upload"
          >
            Загрузить ({{ queue.length }})
          </v-btn>
        </div>

        <div v-if="queue.length" class="mt-3" style="max-height:340px;overflow-y:auto">
          <div v-for="(f, i) in queue" :key="i" class="queue-item">
            <v-icon size="18" color="medium-emphasis">mdi-file-outline</v-icon>
            <span class="name">{{ f.webkitRelativePath || f.name }}</span>
            <span class="size">{{ formatBytes(f.size) }}</span>
            <v-btn icon="mdi-close" size="x-small" variant="text" @click="removeFromQueue(i)" />
          </div>
        </div>
      </v-card-text>
    </v-card>

    <v-card v-if="results.length" class="app-card mt-4">
      <v-card-text class="pa-5">
        <div class="d-flex align-center mb-4" style="gap:12px;flex-wrap:wrap">
          <div class="d-flex align-center" style="gap:8px">
            <div class="text-subtitle-2" style="font-weight:600">Результат загрузки</div>
            <v-progress-circular v-if="waitingPipeline" indeterminate size="16" width="2" color="primary" />
            <span v-if="waitingPipeline" class="text-caption text-medium-emphasis">обработка в pipeline…</span>
          </div>
          <v-spacer />
          <v-chip v-if="loadedCount" size="small" variant="tonal" color="success" prepend-icon="mdi-check">
            Загружено: {{ loadedCount }}
          </v-chip>
          <v-chip v-if="warningCount" size="small" variant="tonal" color="warning" prepend-icon="mdi-alert">
            С предупреждением: {{ warningCount }}
          </v-chip>
          <v-chip v-if="pipelineFailedCount" size="small" variant="tonal" color="error" prepend-icon="mdi-close-circle">
            Ошибка обработки: {{ pipelineFailedCount }}
          </v-chip>
          <v-chip v-if="dupCount" size="small" variant="tonal" color="warning" prepend-icon="mdi-equal">
            Дублей: {{ dupCount }}
          </v-chip>
          <v-chip v-if="rejectedCount" size="small" variant="tonal" color="error" prepend-icon="mdi-alert-circle">
            Отклонено: {{ rejectedCount }}
          </v-chip>
          <v-btn
            v-if="uploading || waitingPipeline"
            size="small"
            variant="tonal"
            color="error"
            prepend-icon="mdi-stop"
            @click="cancelAll"
          >
            Прервать
          </v-btn>
          <v-btn
            v-else
            size="small"
            variant="text"
            prepend-icon="mdi-broom"
            @click="clearResults"
          >
            Очистить
          </v-btn>
        </div>

        <div v-for="(r, i) in results" :key="i" class="upload-row" :class="{ 'is-processing': isInflight(r) }">
          <v-icon :color="rowVisual(r).color" size="20">{{ rowVisual(r).icon }}</v-icon>

          <div style="flex:1;min-width:0">
            <div class="d-flex align-center" style="gap:8px;flex-wrap:wrap">
              <span class="name" style="font-weight:500">{{ r.name }}</span>
              <v-chip size="x-small" variant="tonal" :color="rowVisual(r).color">
                {{ rowLabel(r) }}
              </v-chip>
              <v-chip
                v-if="isInflight(r) && rowStageLabel(r)"
                size="x-small"
                variant="tonal"
                color="info"
                prepend-icon="mdi-cog-sync-outline"
              >
                {{ rowStageLabel(r) }}
              </v-chip>
            </div>

            <div
              v-if="isInflight(r)"
              class="upload-row-progress"
            >
              <div
                v-for="(stage, idx) in VISIBLE_STAGES"
                :key="stage.key"
                class="upload-row-progress-cell"
                :class="{
                  'is-done': idx < stageProgress(r),
                  'is-current': idx === stageProgress(r),
                }"
                :title="stage.label"
              />
            </div>

            <div class="text-caption text-medium-emphasis" style="margin-top:2px">
              <template v-if="r.deduplicated">
                оригинал:
                <v-chip size="x-small" variant="tonal" :color="statusColor(r.original_status)" class="ml-1">
                  {{ statusLabel(r.original_status) }}
                </v-chip>
              </template>
              <template v-if="r.doc_id">
                <span v-if="r.deduplicated"> · </span>
                <router-link :to="`/documents/${r.doc_id}`" style="color:inherit;text-decoration:underline;text-decoration-color:rgba(0,0,0,.2)">
                  {{ r.doc_id.slice(0, 8) }}…
                </router-link>
              </template>
              <span v-if="r.error" class="text-error"> · {{ r.error }}</span>
            </div>
          </div>

          <v-btn
            v-if="r._abort"
            icon="mdi-close"
            size="x-small"
            variant="text"
            title="Отменить загрузку этого файла"
            @click="r._abort.abort()"
          />
          <v-btn
            v-else
            icon="mdi-close"
            size="x-small"
            variant="text"
            title="Убрать из списка"
            @click="dismissRow(i)"
          />
        </div>
      </v-card-text>
    </v-card>
  </div>
</template>
