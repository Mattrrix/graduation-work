<script setup>
import { ref, computed } from 'vue'
import client from '../api/client.js'
import { formatBytes, statusLabel, statusColor, uploadRowVisual, uploadRowLabel } from '../utils/format.js'

const queue = ref([])
const results = ref([])
const uploading = ref(false)
const waitingPipeline = ref(false)
const dragActive = ref(false)
const fileInput = ref(null)
const dirInput = ref(null)

const totalSize = computed(() => queue.value.reduce((s, f) => s + f.size, 0))
const loadedCount = computed(() => results.value.filter((r) => r.ok && !r.deduplicated && r.final_status === 'loaded').length)
const warningCount = computed(() => results.value.filter((r) => r.ok && !r.deduplicated && r.final_status === 'validated_with_errors').length)
const pipelineFailedCount = computed(() => results.value.filter((r) => r.ok && !r.deduplicated && r.final_status === 'failed').length)
const dupCount = computed(() => results.value.filter((r) => r.ok && r.deduplicated).length)
const rejectedCount = computed(() => results.value.filter((r) => !r.ok).length)

function addFiles(files) {
  for (const f of files) queue.value.push(f)
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
  results.value = []
}

async function upload() {
  uploading.value = true
  results.value = []
  for (const f of queue.value) {
    const fd = new FormData()
    fd.append('file', f)
    try {
      const { data } = await client.post('/documents', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      results.value.push({ name: f.webkitRelativePath || f.name, ok: true, final_status: null, ...data })
    } catch (e) {
      results.value.push({
        name: f.webkitRelativePath || f.name,
        ok: false,
        http_status: e.response?.status || 0,
        error: e.response?.data?.detail || e.message,
      })
    }
  }
  uploading.value = false
  queue.value = []

  const docIds = results.value
    .filter((r) => r.ok && !r.deduplicated && r.doc_id)
    .map((r) => r.doc_id)
  if (docIds.length) {
    waitingPipeline.value = true
    try {
      const { data } = await client.post('/documents/wait-final', { doc_ids: docIds })
      const map = data.statuses || {}
      for (const r of results.value) {
        if (r.ok && r.doc_id && map[r.doc_id]) r.final_status = map[r.doc_id]
      }
    } catch (e) {
      // polling failure не критично — UI просто покажет «ожидание» статус
    } finally {
      waitingPipeline.value = false
    }
  }
}

const rowVisual = uploadRowVisual
const rowLabel = uploadRowLabel
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
        </div>

        <div v-for="(r, i) in results" :key="i" class="queue-item">
          <v-icon :color="rowVisual(r).color" size="20">{{ rowVisual(r).icon }}</v-icon>

          <div style="flex:1;min-width:0">
            <div class="d-flex align-center" style="gap:8px;flex-wrap:wrap">
              <span class="name" style="font-weight:500">{{ r.name }}</span>
              <v-chip size="x-small" variant="tonal" :color="rowVisual(r).color">
                {{ rowLabel(r) }}
              </v-chip>
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
        </div>
      </v-card-text>
    </v-card>
  </div>
</template>
