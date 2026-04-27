<script setup>
import { ref, onMounted, computed } from 'vue'
import client from '../api/client.js'
import {
  docTypeOptions,
  edgeCaseHint,
  edgeCaseIcon,
  edgeCaseLabel,
  formatDocType,
  ipModeHint,
  ipModeLabel,
  missingModeHint,
  missingModeLabel,
  statusColor,
  statusLabel,
  uploadRowLabel,
  uploadRowVisual,
} from '../utils/format.js'

const catalog = ref({
  doc_types: [],
  formats: [],
  supported_formats: {},
  edge_cases: [],
  ip_modes: ['random', 'guaranteed', 'all'],
  ip_mode_default: 'random',
  missing_modes: ['random', 'guaranteed', 'all'],
  missing_mode_default: 'random',
  parties_hard_cap: 4,
  max_parties_by_type: {},
  roles_by_type: {},
})
const docTypeItems = computed(() => docTypeOptions(catalog.value.doc_types || []))
const types = ref([])
const formats = ref([])
const count = ref(5)
const junk = ref(3)
const seed = ref('')
const cleanup = ref(true)
const parties = ref(2)
const edgeCases = ref([])
const ipMode = ref('random')
const ipFormsActive = computed(() => edgeCases.value.includes('ip_forms'))
const ipModeOptions = computed(() =>
  (catalog.value.ip_modes || []).map((m) => ({ value: m, title: ipModeLabel(m), hint: ipModeHint(m) }))
)
const missingMode = ref('random')
const missingActive = computed(() => edgeCases.value.includes('missing_optional'))
const missingModeOptions = computed(() =>
  (catalog.value.missing_modes || []).map((m) => ({ value: m, title: missingModeLabel(m), hint: missingModeHint(m) }))
)

const allEdgeCases = computed(() => catalog.value.edge_cases || [])
const allEdgeOn = computed({
  get: () => allEdgeCases.value.length > 0 && allEdgeCases.value.every((e) => edgeCases.value.includes(e)),
  set: (v) => { edgeCases.value = v ? [...allEdgeCases.value] : [] },
})

const generated = ref({ count: 0, files: [] })
const lastGenerate = ref(null)
const lastUpload = ref(null)
const genBusy = ref(false)
const uploadBusy = ref(false)
const clearBusy = ref(false)
const snack = ref({ show: false, text: '', color: 'success' })

const planSize = computed(() => {
  let n = 0
  for (const t of types.value) {
    const sup = catalog.value.supported_formats[t] || []
    for (const f of formats.value) if (sup.includes(f)) n += count.value
  }
  return n + Number(junk.value || 0)
})

async function loadCatalog() {
  const { data } = await client.get('/admin/catalog')
  catalog.value = data
  if (!types.value.length) types.value = [...(data.doc_types || [])]
  if (!formats.value.length) formats.value = [...(data.formats || [])]
  if (data.ip_mode_default) ipMode.value = data.ip_mode_default
  if (data.missing_mode_default) missingMode.value = data.missing_mode_default
}

async function loadGenerated() {
  const { data } = await client.get('/admin/generated')
  generated.value = data
}

async function generate() {
  genBusy.value = true
  try {
    const { data } = await client.post('/admin/generate', {
      types: types.value,
      formats: formats.value,
      count: Number(count.value),
      junk: Number(junk.value),
      seed: seed.value === '' ? null : Number(seed.value),
      parties: Number(parties.value),
      edge_cases: edgeCases.value,
      ip_mode: ipMode.value,
      missing_mode: missingMode.value,
    })
    lastGenerate.value = data
    snack.value = { show: true, text: `Сгенерировано: ${data.count}`, color: 'success' }
    await loadGenerated()
  } catch (e) {
    snack.value = { show: true, text: e.response?.data?.detail || e.message, color: 'error' }
  } finally {
    genBusy.value = false
  }
}

async function generateSmokeTest() {
  types.value = [...(catalog.value.doc_types || [])]
  formats.value = [...(catalog.value.formats || [])]
  count.value = 1
  junk.value = 4
  seed.value = 42
  parties.value = 2
  edgeCases.value = [...(catalog.value.edge_cases || [])]
  ipMode.value = 'guaranteed'
  missingMode.value = 'guaranteed'
  await generate()
}

async function generateMultiSmokeTest() {
  types.value = [...(catalog.value.doc_types || [])]
  formats.value = [...(catalog.value.formats || [])]
  count.value = 1
  junk.value = 0
  seed.value = 7
  parties.value = catalog.value.parties_hard_cap || 4
  edgeCases.value = [...(catalog.value.edge_cases || [])]
  ipMode.value = 'guaranteed'
  missingMode.value = 'guaranteed'
  await generate()
}

async function uploadAll() {
  uploadBusy.value = true
  try {
    const { data } = await client.post('/admin/upload-generated', { cleanup: cleanup.value })
    lastUpload.value = data
    const parts = [`загружено: ${data.loaded}`]
    if (data.warnings) parts.push(`с предупреждением: ${data.warnings}`)
    if (data.duplicates) parts.push(`дублей: ${data.duplicates}`)
    if (data.failed) parts.push(`ошибок: ${data.failed}`)
    snack.value = {
      show: true,
      text: `Из ${data.total} — ${parts.join(', ')}`,
      color: data.failed ? 'error' : data.warnings ? 'warning' : 'success',
    }
    await loadGenerated()
  } catch (e) {
    snack.value = { show: true, text: e.response?.data?.detail || e.message, color: 'error' }
  } finally {
    uploadBusy.value = false
  }
}

const rowVisual = uploadRowVisual
const rowLabel = uploadRowLabel

async function clearGenerated() {
  clearBusy.value = true
  try {
    await client.delete('/admin/generated')
    lastGenerate.value = null
    snack.value = { show: true, text: 'Каталог сгенерированных очищен', color: 'success' }
    await loadGenerated()
  } finally {
    clearBusy.value = false
  }
}

const rolesTable = computed(() => {
  const cap = catalog.value.max_parties_by_type || {}
  const roles = catalog.value.roles_by_type || {}
  return (catalog.value.doc_types || []).map((t) => ({
    type: t,
    label: formatDocType(t),
    cap: cap[t] ?? 0,
    roles: (roles[t] || []).map((r) => r.role_label),
  }))
})

const partyOptions = computed(() => {
  const max = catalog.value.parties_hard_cap || 4
  const out = []
  for (let i = 2; i <= max; i++) out.push(i)
  return out
})

function capStatus(cap) {
  if (parties.value > cap) return 'clipped'
  if (parties.value === cap) return 'maxed'
  return 'fits'
}

onMounted(async () => {
  await loadCatalog()
  await loadGenerated()
})
</script>

<template>
  <div>
    <div class="page-header">
      <h1 class="page-title">Админ-панель</h1>
      <p class="page-subtitle">Генерация синтетических документов и заливка в пайплайн</p>
    </div>

    <v-row>
      <v-col cols="12" md="6">
        <v-card class="app-card" style="height:100%">
          <v-card-text class="pa-5">
            <div class="d-flex align-center mb-4" style="gap:12px">
              <div class="stat-icon stat-icon-indigo">
                <span style="font-weight:700;font-size:14px">1</span>
              </div>
              <div>
                <div class="text-subtitle-1" style="font-weight:600">Сгенерировать</div>
                <div class="text-caption text-medium-emphasis">Тестовые документы для пайплайна</div>
              </div>
            </div>

            <v-select
              v-model="types"
              :items="docTypeItems"
              multiple
              chips
              closable-chips
              label="Типы документов"
              class="mb-2"
            />
            <v-select
              v-model="formats"
              :items="catalog.formats"
              multiple
              chips
              closable-chips
              label="Форматы"
              class="mb-2"
            />
            <v-row dense>
              <v-col cols="4">
                <v-text-field
                  v-model.number="count"
                  type="number"
                  min="1"
                  max="200"
                  label="Кол-во"
                  hint="на тип×формат"
                  persistent-hint
                />
              </v-col>
              <v-col cols="4">
                <v-text-field
                  v-model.number="junk"
                  type="number"
                  min="0"
                  max="200"
                  label="«Мусор»"
                  hint="не-документы"
                  persistent-hint
                />
              </v-col>
              <v-col cols="4">
                <v-text-field
                  v-model="seed"
                  type="number"
                  label="Seed"
                  placeholder="случайный"
                  hint="фикс. → дубли"
                  persistent-hint
                />
              </v-col>
            </v-row>

            <div class="setting-block mt-4">
              <div class="setting-head">
                <v-icon size="18" class="setting-head-icon">mdi-account-multiple-outline</v-icon>
                <span class="setting-title">Контрагентов на документ</span>
                <v-tooltip location="top" max-width="340" open-delay="120">
                  <template #activator="{ props: tipProps }">
                    <span v-bind="tipProps" class="hint-bulb" tabindex="0">
                      <v-icon size="16">mdi-lightbulb-on-outline</v-icon>
                    </span>
                  </template>
                  Каждый тип документа имеет свой реалистичный максимум по количеству контрагентов. Если выбрано больше — для этого типа генератор использует его собственный максимум.
                </v-tooltip>
                <v-spacer />
                <v-btn-toggle
                  v-model="parties"
                  mandatory
                  divided
                  density="compact"
                  color="primary"
                  variant="outlined"
                  class="parties-toggle"
                >
                  <v-btn v-for="n in partyOptions" :key="n" :value="n" size="small">
                    {{ n }}
                  </v-btn>
                </v-btn-toggle>
              </div>
              <v-table density="compact" class="roles-table">
                <thead>
                  <tr>
                    <th style="width:32%">Тип документа</th>
                    <th style="width:14%; text-align:center">Максимум</th>
                    <th>
                      <span class="d-inline-flex align-center" style="gap:4px">
                        Роли
                        <v-icon size="14">mdi-arrow-right</v-icon>
                        <span class="text-caption" style="font-weight:500;text-transform:none;letter-spacing:0">от важной к второстепенной</span>
                      </span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in rolesTable"
                    :key="row.type"
                    :class="`roles-row roles-row-${capStatus(row.cap)}`"
                  >
                    <td>{{ row.label }}</td>
                    <td style="text-align:center">
                      <span class="cap-pill" :data-status="capStatus(row.cap)">
                        {{ row.cap }}
                      </span>
                    </td>
                    <td>
                      <span
                        v-for="(role, i) in row.roles"
                        :key="role"
                        class="role-chip"
                        :class="{ 'role-chip-active': i < Math.min(parties, row.cap) }"
                      ><span class="role-rank">{{ i + 1 }}</span>{{ role }}<span v-if="i < row.roles.length - 1" class="role-sep">·</span></span>
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </div>

            <v-alert
              type="info"
              density="compact"
              class="mt-4"
              border="start"
              variant="tonal"
            >
              Будет создано <strong>{{ planSize }}</strong> файлов
            </v-alert>

            <div class="mt-4 d-flex" style="gap:8px;flex-wrap:wrap">
              <v-btn
                color="primary"
                :loading="genBusy"
                prepend-icon="mdi-shape-outline"
                @click="generate"
              >
                Сгенерировать
              </v-btn>
              <v-tooltip
                location="top"
                text="По 1 файлу каждого типа во всех форматах + 4 «мусорных» файла + все особые случаи. Режимы: ИП — «Гарантированно ≥1», пропуски полей — «Гарантированно ≥1». parties=2 — реалистичный baseline. Seed=42."
              >
                <template #activator="{ props: tipProps }">
                  <v-btn
                    v-bind="tipProps"
                    variant="tonal"
                    color="info"
                    :loading="genBusy"
                    prepend-icon="mdi-test-tube"
                    @click="generateSmokeTest"
                  >
                    Smoke-test-duo
                  </v-btn>
                </template>
              </v-tooltip>
              <v-tooltip
                location="top"
                text="По 1 файлу каждого типа во всех форматах. parties=максимум типа (до 4), все особые случаи включены. Режимы: ИП — «Гарантированно ≥1», пропуски полей — «Гарантированно ≥1». Стресс-тест для multi-entity NER. Seed=7."
              >
                <template #activator="{ props: tipProps }">
                  <v-btn
                    v-bind="tipProps"
                    variant="tonal"
                    color="warning"
                    :loading="genBusy"
                    prepend-icon="mdi-account-multiple-plus-outline"
                    @click="generateMultiSmokeTest"
                  >
                    Smoke-test-multi
                  </v-btn>
                </template>
              </v-tooltip>
              <v-btn
                variant="text"
                :loading="clearBusy"
                prepend-icon="mdi-delete-sweep"
                @click="clearGenerated"
              >
                Очистить каталог
              </v-btn>
            </div>

            <v-alert
              v-if="lastGenerate"
              density="compact"
              type="success"
              class="mt-4"
              variant="tonal"
            >
              Создано <strong>{{ lastGenerate.count }}</strong> файлов в <code>{{ lastGenerate.out_dir }}</code>
              <span v-if="lastGenerate.parties != null">
                · контрагентов: <strong>{{ lastGenerate.parties }}</strong>
              </span>
              <span v-if="lastGenerate.edge_cases?.length">
                · edge-кейсы: <strong>{{ lastGenerate.edge_cases.map(edgeCaseLabel).join(', ') }}</strong>
              </span>
            </v-alert>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" class="right-stack">
        <v-card class="app-card">
          <v-card-text class="pa-5">
            <div class="d-flex align-center mb-4" style="gap:12px">
              <div class="stat-icon stat-icon-amber">
                <v-icon size="18">mdi-flask-outline</v-icon>
              </div>
              <div style="min-width:0">
                <div class="d-flex align-center" style="gap:6px">
                  <div class="text-subtitle-1" style="font-weight:600">Особые случаи</div>
                  <v-tooltip location="top" max-width="360" open-delay="120">
                    <template #activator="{ props: tipProps }">
                      <span v-bind="tipProps" class="hint-bulb" tabindex="0">
                        <v-icon size="16">mdi-lightbulb-on-outline</v-icon>
                      </span>
                    </template>
                    Тестовый материал для будущего LLM-NER (Phase 3). Каждый кейс воспроизводит ситуацию, на которой текущий regex-парсер стабильно ошибается — на этих документах будет сравниваться качество regex и LLM, чтобы измерить выгоду перехода.
                  </v-tooltip>
                </div>
                <div class="text-caption text-medium-emphasis">Дополнительные модификации к параметрам генерации</div>
              </div>
              <v-spacer />
              <a
                href="#"
                class="select-all-link"
                :class="{ 'select-all-link-active': allEdgeOn }"
                @click.prevent="allEdgeOn = !allEdgeOn"
              >
                <v-icon size="14">{{ allEdgeOn ? 'mdi-close' : 'mdi-check-all' }}</v-icon>
                {{ allEdgeOn ? 'Снять все' : 'Выбрать все' }}
              </a>
            </div>

            <v-row dense class="edge-grid">
              <v-col v-for="ec in allEdgeCases" :key="ec" cols="12" sm="6">
                <label
                  class="edge-card"
                  :class="{ 'edge-card-active': edgeCases.includes(ec) }"
                >
                  <v-checkbox
                    v-model="edgeCases"
                    :value="ec"
                    density="compact"
                    hide-details
                    class="edge-checkbox"
                  />
                  <v-icon size="18" class="edge-icon">{{ edgeCaseIcon(ec) }}</v-icon>
                  <div class="edge-text">
                    <div class="edge-label">{{ edgeCaseLabel(ec) }}</div>
                    <div class="edge-hint">{{ edgeCaseHint(ec) }}</div>
                    <div
                      v-if="ec === 'ip_forms' && ipFormsActive"
                      class="ip-modes"
                      @click.stop.prevent
                    >
                      <v-btn-toggle
                        v-model="ipMode"
                        mandatory
                        divided
                        density="compact"
                        color="primary"
                        variant="outlined"
                        class="ip-modes-toggle"
                      >
                        <v-btn
                          v-for="m in ipModeOptions"
                          :key="m.value"
                          :value="m.value"
                          size="x-small"
                          :title="m.hint"
                        >{{ m.title }}</v-btn>
                      </v-btn-toggle>
                    </div>
                    <div
                      v-if="ec === 'missing_optional' && missingActive"
                      class="ip-modes"
                      @click.stop.prevent
                    >
                      <v-btn-toggle
                        v-model="missingMode"
                        mandatory
                        divided
                        density="compact"
                        color="primary"
                        variant="outlined"
                        class="ip-modes-toggle"
                      >
                        <v-btn
                          v-for="m in missingModeOptions"
                          :key="m.value"
                          :value="m.value"
                          size="x-small"
                          :title="m.hint"
                        >{{ m.title }}</v-btn>
                      </v-btn-toggle>
                    </div>
                  </div>
                </label>
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>

        <v-card class="app-card upload-card">
          <v-card-text class="pa-5">
            <div class="d-flex align-center mb-4" style="gap:12px">
              <div class="stat-icon stat-icon-emerald">
                <span style="font-weight:700;font-size:14px">2</span>
              </div>
              <div>
                <div class="text-subtitle-1" style="font-weight:600">Залить в пайплайн</div>
                <div class="text-caption text-medium-emphasis">Отправить сгенерированные файлы на обработку</div>
              </div>
            </div>

            <div class="d-flex align-center pa-3 mb-3" style="gap:12px;border:1px solid rgb(var(--v-theme-border));border-radius:12px;background:rgb(var(--v-theme-surface-variant))">
              <v-icon size="22" color="primary">mdi-folder-outline</v-icon>
              <div style="flex:1">
                <div class="text-body-2" style="font-weight:500">В каталоге</div>
                <div class="text-caption text-medium-emphasis">/data/files/generated</div>
              </div>
              <div class="text-h6" style="font-weight:600;font-variant-numeric:tabular-nums">{{ generated.count }}</div>
            </div>

            <v-checkbox
              v-model="cleanup"
              label="Удалить временные файлы после заливки"
              density="compact"
              hide-details
              class="mb-3"
            />

            <v-btn
              color="success"
              size="default"
              :disabled="!generated.count"
              :loading="uploadBusy"
              prepend-icon="mdi-rocket-launch-outline"
              block
              @click="uploadAll"
            >
              Загрузить все ({{ generated.count }})
            </v-btn>

            <div v-if="lastUpload" class="mt-4">
              <div class="d-flex flex-wrap" style="gap:8px">
                <v-chip variant="tonal" color="primary" prepend-icon="mdi-file-multiple-outline">
                  Всего: <strong class="ml-1">{{ lastUpload.total }}</strong>
                </v-chip>
                <v-chip v-if="lastUpload.loaded" variant="tonal" color="success" prepend-icon="mdi-check-circle">
                  В БД: <strong class="ml-1">{{ lastUpload.loaded }}</strong>
                </v-chip>
                <v-chip v-if="lastUpload.warnings" variant="tonal" color="warning" prepend-icon="mdi-alert-outline">
                  С предупреждением: <strong class="ml-1">{{ lastUpload.warnings }}</strong>
                </v-chip>
                <v-chip v-if="lastUpload.duplicates" variant="tonal" color="info" prepend-icon="mdi-equal">
                  Дублей: <strong class="ml-1">{{ lastUpload.duplicates }}</strong>
                </v-chip>
                <v-chip v-if="lastUpload.failed" variant="tonal" color="error" prepend-icon="mdi-close-circle">
                  Ошибок: <strong class="ml-1">{{ lastUpload.failed }}</strong>
                </v-chip>
              </div>
            </div>

            <v-expansion-panels v-if="lastUpload" class="mt-3" variant="accordion">
              <v-expansion-panel title="Подробный отчёт по файлам" rounded="lg">
                <v-expansion-panel-text>
                  <div style="max-height:420px;overflow-y:auto">
                    <div v-for="(r, i) in lastUpload.results" :key="i" class="queue-item">
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
                  </div>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3500" location="top right">
      {{ snack.text }}
    </v-snackbar>
  </div>
</template>

<style scoped>
.right-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.upload-card {
  border-top: 3px solid rgba(var(--v-theme-success), 0.55);
}
.setting-block {
  border: 1px solid rgb(var(--v-theme-border));
  border-radius: 12px;
  padding: 14px 16px;
  background: rgb(var(--v-theme-surface));
}
.setting-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.setting-head-icon {
  color: rgb(var(--v-theme-primary));
  opacity: 0.85;
}
.setting-title {
  font-size: 0.875rem;
  font-weight: 600;
  letter-spacing: 0.1px;
}
.parties-toggle {
  height: 32px;
  border-radius: 8px;
  overflow: hidden;
}
.parties-toggle :deep(.v-btn) {
  min-width: 36px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.setting-hint {
  font-size: 0.78rem;
  line-height: 1.45;
  color: rgba(var(--v-theme-on-surface), 0.6);
  margin-top: 2px;
}
.hint-bulb {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  cursor: help;
  outline: none;
  color: rgba(var(--v-theme-on-surface), 0.35);
  transition: color 220ms ease, background 220ms ease, filter 220ms ease, transform 220ms ease;
}
.hint-bulb:hover,
.hint-bulb:focus-visible {
  color: #F5C518;
  background: rgba(245, 197, 24, 0.12);
  filter: drop-shadow(0 0 6px rgba(245, 197, 24, 0.55));
  transform: translateY(-1px);
}
.v-theme--light .hint-bulb:hover,
.v-theme--light .hint-bulb:focus-visible {
  color: #B45309;
  background: rgba(180, 83, 9, 0.10);
  filter: drop-shadow(0 0 5px rgba(217, 119, 6, 0.40));
}
.hint-bulb:hover :deep(.v-icon),
.hint-bulb:focus-visible :deep(.v-icon) {
  animation: bulb-flicker 1.6s ease-in-out infinite;
}
@keyframes bulb-flicker {
  0%, 100% { opacity: 1; }
  45% { opacity: 0.85; }
  50% { opacity: 0.7; }
  55% { opacity: 0.95; }
}
.edge-grid {
  margin-top: 4px;
}
.edge-card {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid rgb(var(--v-theme-border));
  border-radius: 10px;
  background: rgb(var(--v-theme-surface-variant));
  cursor: pointer;
  transition: border-color 120ms ease, background 120ms ease;
  height: 100%;
}
.edge-card:hover {
  border-color: rgba(var(--v-theme-primary), 0.5);
}
.edge-card-active {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.07);
}
.edge-checkbox {
  flex: 0 0 auto;
  margin-top: -6px;
  margin-left: -6px;
}
.edge-icon {
  flex: 0 0 auto;
  margin-top: 2px;
  color: rgb(var(--v-theme-primary));
  opacity: 0.85;
}
.edge-text {
  flex: 1;
  min-width: 0;
}
.edge-label {
  font-size: 0.875rem;
  font-weight: 600;
  line-height: 1.25;
}
.edge-hint {
  font-size: 0.75rem;
  line-height: 1.4;
  color: rgba(var(--v-theme-on-surface), 0.6);
  margin-top: 2px;
}
.ip-modes {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.ip-modes-toggle {
  height: 26px;
  border-radius: 7px;
  overflow: hidden;
}
.ip-modes-toggle :deep(.v-btn) {
  font-size: 0.7rem !important;
  font-weight: 500;
  padding: 0 8px !important;
  min-width: 0;
  letter-spacing: 0;
}
.roles-table {
  background: transparent !important;
}
.roles-table :deep(th),
.roles-table :deep(td) {
  font-size: 0.82rem;
  padding: 6px 10px !important;
  border-bottom: 1px solid rgba(var(--v-theme-border), 0.6) !important;
}
.roles-table :deep(thead th) {
  font-weight: 600;
  letter-spacing: 0.1px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  border-bottom: 1px solid rgb(var(--v-theme-border)) !important;
}
.roles-table :deep(tbody tr) {
  transition: background 140ms ease, opacity 140ms ease;
}
.roles-row-fits :deep(td:first-child) {
  color: rgba(var(--v-theme-on-surface), 0.85);
}
.roles-row-maxed {
  background: rgba(var(--v-theme-primary), 0.06);
}
.roles-row-maxed :deep(td:first-child) {
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
}
.roles-row-clipped {
  background: rgba(var(--v-theme-warning), 0.07);
}
.roles-row-clipped :deep(td:first-child) {
  color: rgb(var(--v-theme-warning));
  font-weight: 500;
}
.roles-row-clipped :deep(td) {
  opacity: 0.9;
}
.cap-pill {
  display: inline-block;
  min-width: 28px;
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  font-size: 0.8rem;
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.cap-pill[data-status='maxed'] {
  background: rgba(var(--v-theme-primary), 0.18);
  color: rgb(var(--v-theme-primary));
}
.cap-pill[data-status='clipped'] {
  background: rgba(var(--v-theme-warning), 0.18);
  color: rgb(var(--v-theme-warning));
}
.role-chip {
  display: inline-flex;
  align-items: center;
  font-size: 0.8rem;
  color: rgba(var(--v-theme-on-surface), 0.35);
  transition: color 140ms ease;
}
.role-chip-active {
  color: rgb(var(--v-theme-on-surface));
}
.role-rank {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  margin-right: 5px;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: rgba(var(--v-theme-on-surface), 0.45);
  transition: background 140ms ease, color 140ms ease;
}
.role-chip-active .role-rank {
  background: rgba(var(--v-theme-primary), 0.18);
  color: rgb(var(--v-theme-primary));
}
.role-sep {
  display: inline-block;
  margin: 0 6px;
  color: rgba(var(--v-theme-on-surface), 0.25);
}
.select-all-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.78rem;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.65);
  text-decoration: none;
  cursor: pointer;
  transition: color 120ms ease;
}
.select-all-link:hover {
  color: rgb(var(--v-theme-primary));
}
.select-all-link-active {
  color: rgb(var(--v-theme-primary));
}
</style>
