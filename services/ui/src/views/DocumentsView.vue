<script setup>
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import client from '../api/client.js'
import {
  formatDateTime,
  formatDocType,
  docTypeOptions,
  formatAmount,
  fileIcon,
  fileIconColor,
  rowStatusDisplay,
} from '../utils/format.js'

const route = useRoute()
const router = useRouter()

const items = ref([])
const total = ref(0)
const loading = ref(false)
const search = ref('')
const status = ref(null)
const docType = ref(null)
const page = ref(1)
const pageSize = ref(20)
const sortBy = ref([{ key: 'created_at', order: 'desc' }])

function hydrateFromQuery() {
  const q = route.query
  if (typeof q.q === 'string') search.value = q.q
  if (typeof q.status === 'string') status.value = q.status
  if (typeof q.type === 'string') docType.value = q.type
  if (q.page) page.value = Math.max(1, parseInt(q.page, 10) || 1)
  if (q.size) pageSize.value = parseInt(q.size, 10) || 20
  if (q.sort_by) sortBy.value = [{ key: String(q.sort_by), order: q.sort_order === 'asc' ? 'asc' : 'desc' }]
}
hydrateFromQuery()

function syncQuery() {
  const q = {}
  if (search.value) q.q = search.value
  if (status.value) q.status = status.value
  if (docType.value) q.type = docType.value
  if (page.value > 1) q.page = String(page.value)
  if (pageSize.value !== 20) q.size = String(pageSize.value)
  const sb = sortBy.value[0]
  if (sb && (sb.key !== 'created_at' || sb.order !== 'desc')) {
    q.sort_by = sb.key
    q.sort_order = sb.order
  }
  if (JSON.stringify(q) !== JSON.stringify(route.query)) {
    router.replace({ query: q })
  }
}

const selected = ref([])
const bulkDialog = ref(false)
const bulkMode = ref('selected')
const bulkBusy = ref(false)
const snack = ref({ show: false, text: '', color: 'success' })

const stats = ref({ total: 0, loaded: 0, warnings: 0, errors: 0 })

const STATUSES = [
  { value: 'extracted', title: 'Обрабатывается' },
  { value: 'loaded', title: 'В БД' },
  { value: 'validated_with_errors', title: 'С предупреждением' },
  { value: 'failed', title: 'Ошибка' },
]
const TYPES = docTypeOptions(['invoice', 'act', 'contract', 'payment_order', 'waybill', 'upd'])

const statCards = computed(() => [
  {
    label: 'Всего документов',
    value: stats.value.total,
    icon: 'mdi-file-document-outline',
    tone: 'indigo',
    filter: null,
  },
  {
    label: 'Загружено в БД',
    value: stats.value.loaded,
    icon: 'mdi-database-check-outline',
    tone: 'emerald',
    filter: 'loaded',
  },
  {
    label: 'С предупреждением',
    value: stats.value.warnings,
    icon: 'mdi-alert-outline',
    tone: 'amber',
    filter: 'validated_with_errors',
  },
  {
    label: 'С ошибками',
    value: stats.value.errors,
    icon: 'mdi-close-circle-outline',
    tone: 'red',
    filter: 'failed',
  },
])

function applyStatCardFilter(card) {
  status.value = card.filter
  page.value = 1
}

async function loadStats() {
  try {
    const { data } = await client.get('/documents/stats')
    const by = data.by_status || {}
    stats.value = {
      total: data.total || 0,
      loaded: by.loaded || 0,
      warnings: by.validated_with_errors || 0,
      errors: by.failed || 0,
    }
  } catch {}
}

const TERMINAL_STATUSES = new Set(['loaded', 'validated_with_errors', 'failed'])

async function load({ silent = false } = {}) {
  syncQuery()
  if (!silent) loading.value = true
  try {
    if (search.value) {
      const { data } = await client.get('/search', { params: { q: search.value, limit: pageSize.value } })
      items.value = data.items
      total.value = data.items.length
    } else {
      const params = { limit: pageSize.value, offset: (page.value - 1) * pageSize.value }
      if (status.value) params.status = status.value
      if (docType.value) params.doc_type = docType.value
      if (sortBy.value.length) {
        params.sort_by = sortBy.value[0].key
        params.sort_order = sortBy.value[0].order
      }
      const { data } = await client.get('/documents', { params })
      items.value = data.items
      total.value = data.total
    }
  } finally {
    if (!silent) loading.value = false
  }
}

let pollTimer = null
async function pollTick() {
  const hasInflight = items.value.some((i) => !TERMINAL_STATUSES.has(i.status))
  if (!hasInflight) {
    stopPolling()
    return
  }
  await Promise.all([load({ silent: true }), loadStats()])
}
function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(pollTick, 2500)
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

watch([status, docType, pageSize], () => { page.value = 1 })
watch(sortBy, () => { page.value = 1 }, { deep: true })
watch([page, status, docType, pageSize, sortBy], () => load(), { deep: true })

watch(items, (list) => {
  const hasInflight = list.some((i) => !TERMINAL_STATUSES.has(i.status))
  if (hasInflight) startPolling()
  else stopPolling()
}, { deep: true })

const isCustomSort = computed(() => {
  const sb = sortBy.value[0]
  return !sb || sb.key !== 'created_at' || sb.order !== 'desc'
})
const hasActiveFilters = computed(() =>
  !!search.value || !!status.value || !!docType.value || isCustomSort.value || pageSize.value !== 20,
)

function clearFilters() {
  search.value = ''
  status.value = null
  docType.value = null
  page.value = 1
  pageSize.value = 20
  sortBy.value = [{ key: 'created_at', order: 'desc' }]
}

function openBulk(mode) {
  bulkMode.value = mode
  bulkDialog.value = true
}

const bulkLabel = computed(() => {
  if (bulkMode.value === 'selected') return `Удалить выбранные (${selected.value.length})`
  if (bulkMode.value === 'failed')   return 'Удалить все «Ошибка»'
  if (bulkMode.value === 'warnings') return 'Удалить все «С предупреждением»'
  if (bulkMode.value === 'all')      return 'Очистить базу полностью'
  return ''
})

async function runBulk() {
  bulkBusy.value = true
  try {
    let payload = {}
    if (bulkMode.value === 'selected') {
      if (!selected.value.length) { bulkDialog.value = false; return }
      payload = { doc_ids: selected.value }
    } else if (bulkMode.value === 'failed') {
      payload = { status: 'failed' }
    } else if (bulkMode.value === 'warnings') {
      payload = { status: 'validated_with_errors' }
    } else if (bulkMode.value === 'all') {
      payload = { all: true }
    }
    const { data } = await client.post('/documents/bulk-delete', payload)
    snack.value = { show: true, text: `Удалено: ${data.deleted}`, color: 'success' }
    selected.value = []
    bulkDialog.value = false
    await Promise.all([load(), loadStats()])
  } catch (e) {
    snack.value = { show: true, text: e.response?.data?.detail || e.message, color: 'error' }
  } finally {
    bulkBusy.value = false
  }
}

const DEFAULT_WIDTHS = {
  filename: 280,
  doc_type: 130,
  number: 130,
  doc_date: 110,
  counterparty_name: 220,
  counterparty_inn: 130,
  amount_total: 140,
  status: 170,
  created_at: 180,
}
const colWidths = ref({ ...DEFAULT_WIDTHS })

const headers = computed(() => [
  { title: 'Файл',       key: 'filename',          width: colWidths.value.filename },
  { title: 'Тип',        key: 'doc_type',          width: colWidths.value.doc_type },
  { title: 'Номер',      key: 'number',            width: colWidths.value.number },
  { title: 'Дата',       key: 'doc_date',          width: colWidths.value.doc_date },
  { title: 'Контрагент', key: 'counterparty_name', width: colWidths.value.counterparty_name },
  { title: 'ИНН',        key: 'counterparty_inn',  width: colWidths.value.counterparty_inn },
  { title: 'Сумма',      key: 'amount_total', align: 'end', width: colWidths.value.amount_total },
  { title: 'Статус',     key: 'status',            width: colWidths.value.status },
  { title: 'Создан',     key: 'created_at',        width: colWidths.value.created_at },
])

let resizing = null
const MIN_COL_WIDTH = 70
const MAX_COL_WIDTH = 600

function onResizeStart(e, key) {
  e.preventDefault()
  e.stopPropagation()
  resizing = { key, startX: e.clientX, startWidth: colWidths.value[key] }
  window.addEventListener('pointermove', onResizeMove)
  window.addEventListener('pointerup', onResizeEnd)
  document.body.classList.add('col-resizing')
}

function onResizeMove(e) {
  if (!resizing) return
  const dx = e.clientX - resizing.startX
  const next = Math.max(MIN_COL_WIDTH, Math.min(MAX_COL_WIDTH, resizing.startWidth + dx))
  colWidths.value[resizing.key] = next
}

function onResizeEnd() {
  resizing = null
  window.removeEventListener('pointermove', onResizeMove)
  window.removeEventListener('pointerup', onResizeEnd)
  document.body.classList.remove('col-resizing')
}

function resetColumnWidths() {
  colWidths.value = { ...DEFAULT_WIDTHS }
}

onMounted(async () => {
  await Promise.all([load(), loadStats()])
})
onBeforeUnmount(stopPolling)
</script>

<template>
  <div>
    <div class="page-header d-flex flex-wrap align-center" style="gap:12px">
      <div>
        <h1 class="page-title">Документы</h1>
        <p class="page-subtitle">Загруженные и обработанные документы пайплайна</p>
      </div>
      <v-spacer />
      <v-btn
        v-if="selected.length"
        color="error"
        variant="tonal"
        prepend-icon="mdi-delete-outline"
        @click="openBulk('selected')"
      >
        Удалить ({{ selected.length }})
      </v-btn>
      <v-menu>
        <template #activator="{ props }">
          <v-btn v-bind="props" variant="tonal" prepend-icon="mdi-dots-horizontal">
            Действия
          </v-btn>
        </template>
        <v-list density="compact" rounded="lg" min-width="260">
          <v-list-item @click="openBulk('failed')" prepend-icon="mdi-close-circle-outline">
            <v-list-item-title>Удалить все «Ошибка»</v-list-item-title>
          </v-list-item>
          <v-list-item @click="openBulk('warnings')" prepend-icon="mdi-alert-outline">
            <v-list-item-title>Удалить все «С предупреждением»</v-list-item-title>
          </v-list-item>
          <v-divider />
          <v-list-item @click="openBulk('all')" prepend-icon="mdi-database-remove" class="text-error">
            <v-list-item-title>Очистить базу полностью</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
    </div>

    <v-row class="mb-4" dense>
      <v-col v-for="s in statCards" :key="s.label" cols="6" md="3">
        <button
          type="button"
          class="stat-card stat-card-clickable"
          :class="[
            `stat-card-tone-${s.tone}`,
            { 'stat-card-active': status === s.filter && (s.filter !== null || !status) },
          ]"
          :title="s.filter ? `Показать только: ${s.label}` : 'Показать все документы'"
          @click="applyStatCardFilter(s)"
        >
          <div class="stat-head">
            <div class="stat-icon" :class="`stat-icon-${s.tone}`">
              <v-icon :icon="s.icon" size="20" />
            </div>
            <div class="stat-label">{{ s.label }}</div>
          </div>
          <div class="stat-value">{{ s.value.toLocaleString('ru-RU') }}</div>
        </button>
      </v-col>
    </v-row>

    <v-card class="app-card">
      <v-card-text class="pa-5">
        <v-row dense class="mb-3">
          <v-col cols="12" md="6">
            <v-text-field
              v-model="search"
              label="Поиск (ФИО / ИНН / номер / содержимое)"
              prepend-inner-icon="mdi-magnify"
              clearable
              hide-details
              @keyup.enter="load"
              @click:clear="() => { search = ''; load() }"
            />
          </v-col>
          <v-col cols="6" md="3">
            <v-select v-model="status" :items="STATUSES" label="Статус" clearable hide-details />
          </v-col>
          <v-col cols="6" md="3">
            <v-select v-model="docType" :items="TYPES" label="Тип документа" clearable hide-details />
          </v-col>
        </v-row>

        <div v-if="hasActiveFilters" class="d-flex align-center mb-3" style="gap:8px">
          <span class="text-caption text-medium-emphasis">
            <template v-if="search || status || docType">Фильтры активны</template>
            <template v-else-if="isCustomSort">Сортировка изменена</template>
            <template v-else>Параметры таблицы изменены</template>
          </span>
          <v-btn variant="tonal" size="x-small" prepend-icon="mdi-filter-off-outline" @click="clearFilters">
            Сбросить
          </v-btn>
        </div>

        <v-data-table-server
          v-model="selected"
          v-model:page="page"
          v-model:items-per-page="pageSize"
          v-model:sort-by="sortBy"
          :items="items"
          :items-length="total"
          :headers="headers"
          :loading="loading"
          :items-per-page-options="[10, 20, 50, 100]"
          item-value="doc_id"
          show-select
          must-sort
          density="comfortable"
          class="resizable-table"
          @click:row="(_, { item }) => $router.push(`/documents/${item.doc_id}`)"
          hover
        >
          <template
            v-for="h in headers"
            :key="`hdr-${h.key}`"
            #[`header.${h.key}`]="{ column, getSortIcon }"
          >
            <span class="th-content">
              <span class="th-title">{{ column.title }}</span>
              <v-icon v-if="column.sortable !== false" size="16" class="th-sort-icon">
                {{ getSortIcon ? getSortIcon(column) : 'mdi-arrow-up' }}
              </v-icon>
            </span>
            <span
              class="resize-handle"
              title="Перетащите чтобы изменить ширину столбца"
              @pointerdown="onResizeStart($event, h.key)"
              @click.stop
            />
          </template>

          <template #item.filename="{ item }">
            <div class="d-flex align-center" style="gap:10px;min-width:0">
              <v-icon :icon="fileIcon(item.filename)" :color="fileIconColor(item.filename)" size="22" />
              <span class="filename-cell" :title="item.filename">{{ item.filename }}</span>
            </div>
          </template>
          <template #item.doc_type="{ item }">
            <v-chip v-if="item.doc_type" size="small" variant="tonal" color="primary">
              {{ formatDocType(item.doc_type) }}
            </v-chip>
            <span v-else class="text-medium-emphasis">—</span>
          </template>
          <template #item.number="{ item }">
            <span class="mono">{{ item.number || '—' }}</span>
          </template>
          <template #item.counterparty_inn="{ item }">
            <span class="mono">{{ item.counterparty_inn || '—' }}</span>
          </template>
          <template #item.counterparty_name="{ item }">
            {{ item.counterparty_name || '—' }}
          </template>
          <template #item.doc_date="{ item }">
            <span>{{ item.doc_date || '—' }}</span>
          </template>
          <template #item.amount_total="{ item }">
            <span class="mono" style="font-weight:500">{{ item.amount_total ? formatAmount(item.amount_total, item.currency) : '—' }}</span>
          </template>
          <template #item.status="{ item }">
            <v-chip
              size="small"
              variant="tonal"
              :color="rowStatusDisplay(item).color"
              :prepend-icon="rowStatusDisplay(item).icon"
            >
              {{ rowStatusDisplay(item).label }}
            </v-chip>
          </template>
          <template #item.created_at="{ item }">
            <span class="text-medium-emphasis">{{ formatDateTime(item.created_at) }}</span>
          </template>

          <template #no-data>
            <div class="empty-state">
              <v-icon>mdi-folder-open-outline</v-icon>
              <div class="text-body-2">Документы не найдены</div>
              <div class="text-caption mt-1">Попробуйте сбросить фильтры или загрузить новые документы</div>
            </div>
          </template>
        </v-data-table-server>
      </v-card-text>
    </v-card>

    <v-dialog v-model="bulkDialog" max-width="480">
      <v-card class="app-card">
        <v-card-title class="pt-5 px-5">Подтвердите удаление</v-card-title>
        <v-card-text class="px-5">
          <v-alert v-if="bulkMode === 'all'" type="error" density="compact" class="mb-3">
            <strong>Внимание!</strong> Будут удалены ВСЕ документы и весь аудит-трейл. Это необратимо.
          </v-alert>
          <p class="text-body-2">{{ bulkLabel }}?</p>
        </v-card-text>
        <v-card-actions class="px-5 pb-5">
          <v-spacer />
          <v-btn variant="text" @click="bulkDialog = false">Отмена</v-btn>
          <v-btn color="error" :loading="bulkBusy" @click="runBulk">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3000" location="top right">
      {{ snack.text }}
    </v-snackbar>
  </div>
</template>

<style scoped>
.stat-card-clickable {
  width: 100%;
  text-align: left;
  font: inherit;
  color: inherit;
  cursor: pointer;
  appearance: none;
  outline: none;
  --tone-rgb: var(--v-theme-primary);
}
.stat-card-tone-indigo  { --tone-rgb: var(--v-theme-primary); }
.stat-card-tone-emerald { --tone-rgb: var(--v-theme-success); }
.stat-card-tone-amber   { --tone-rgb: var(--v-theme-warning); }
.stat-card-tone-red     { --tone-rgb: var(--v-theme-error); }
.stat-card-clickable .stat-value {
  color: rgb(var(--tone-rgb));
}
.stat-card-clickable:focus-visible {
  border-color: rgb(var(--tone-rgb));
  box-shadow: 0 0 0 3px rgba(var(--tone-rgb), 0.22);
}
.stat-card-active {
  border-color: rgb(var(--tone-rgb)) !important;
  background: linear-gradient(180deg,
    rgba(var(--tone-rgb), 0.10) 0%,
    rgb(var(--v-theme-surface)) 60%
  ) !important;
  box-shadow: 0 8px 24px -10px rgba(var(--tone-rgb), 0.35);
}
.stat-card-active::after {
  content: '';
  display: block;
  position: relative;
  height: 2px;
  margin-top: -10px;
  border-radius: 2px;
  background: rgb(var(--tone-rgb));
  opacity: 0.85;
}

.resizable-table :deep(table) {
  table-layout: fixed;
}
.resizable-table :deep(thead th) {
  position: relative;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.resizable-table :deep(tbody td) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.th-content {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.th-title {
  overflow: hidden;
  text-overflow: ellipsis;
}
.th-sort-icon {
  opacity: 0.55;
}
.resize-handle {
  position: absolute;
  top: 0;
  right: 0;
  width: 8px;
  height: 100%;
  cursor: col-resize;
  user-select: none;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
}
.resize-handle::after {
  content: '';
  display: block;
  width: 2px;
  height: 60%;
  background: rgba(var(--v-theme-on-surface), 0.15);
  border-radius: 2px;
  transition: background 120ms ease;
}
.resize-handle:hover::after {
  background: rgb(var(--v-theme-primary));
  width: 3px;
  height: 70%;
}
.filename-cell {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
</style>

<style>
body.col-resizing,
body.col-resizing * {
  cursor: col-resize !important;
  user-select: none !important;
}
</style>
