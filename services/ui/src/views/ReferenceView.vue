<script setup>
import { ref, computed, onMounted } from 'vue'
import client from '../api/client.js'
import {
  JUNK_KIND_META,
  PIPELINE_STAGES,
  TECH_STACK,
  edgeCaseHint,
  edgeCaseIcon,
  edgeCaseLabel,
  formatDocType,
  ipModeHint,
  ipModeLabel,
  missingModeHint,
  missingModeLabel,
} from '../utils/format.js'

// Source-of-truth data: типы, форматы, cap, роли, edge-cases — приходят из catalog
// (тот же эндпоинт что использует AdminView, чтобы справка не расходилась с генератором).
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

async function loadCatalog() {
  const { data } = await client.get('/admin/catalog')
  catalog.value = data
}

const docTypeRows = computed(() =>
  (catalog.value.doc_types || []).map((t) => ({
    type: t,
    label: formatDocType(t),
    formats: catalog.value.supported_formats[t] || [],
    cap: catalog.value.max_parties_by_type[t] ?? 0,
    roles: (catalog.value.roles_by_type[t] || []).map((r) => r.role_label),
  }))
)

// Порядок проверки правил классификатора. Сначала самые однозначные заголовки,
// к низу — более общие фразы, которые могут встречаться внутри других видов.
const classifierRules = [
  { id: 'payment_order', label: 'Платёжное поручение',
    triggers: ['«платежное поручение» / «платёжное поручение»'],
    note: 'Самый однозначный заголовок, проверяется первым.' },
  { id: 'upd', label: 'УПД',
    triggers: ['«универсальный передаточный документ»', '«УПД-...»'],
    note: 'Уникальная фраза, не встречается в других видах документов.' },
  { id: 'waybill', label: 'ТОРГ-12',
    triggers: ['«ТОРГ-12»', '«товарная накладная»'],
    note: 'Стандартный код формы и устойчивое название накладной — не пересекаются с другими видами.' },
  { id: 'act', label: 'Акт',
    triggers: ['«акт № ...» / «акт выполненных» / «акт оказанных» / «акт приёмки» / «акт сдачи»'],
    note: 'Слово «акт» встречается и в нерелевантных текстах, поэтому ищется только в связке с дополнительным маркером.' },
  { id: 'contract', label: 'Договор',
    triggers: ['«договор № ...»', '«контракт № ...»'],
    note: 'Слово «договор» само по себе общее, но связка с «№» однозначно указывает на заголовок документа.' },
  { id: 'invoice', label: 'Счёт-фактура',
    triggers: ['«счёт-фактура» + (№ или цифры)', '«счёт № ...» / «счёт на оплату»'],
    note: 'Слово «счёт» часто встречается в платёжных поручениях (в назначении платежа), поэтому правило стоит последним.' },
]

const filenameHints = [
  { type: 'payment_order', tokens: ['payment_order', 'payment-order', 'плат'] },
  { type: 'upd',          tokens: ['upd', 'упд'] },
  { type: 'waybill',      tokens: ['waybill', 'торг', 'накладн'] },
  { type: 'invoice',      tokens: ['invoice', 'счет', 'счёт'] },
  { type: 'act',          tokens: ['act', 'акт'] },
  { type: 'contract',     tokens: ['contract', 'договор'] },
]

const validators = [
  { code: 'inn', label: 'ИНН',
    check: 'Контрольная сумма по алгоритму ФНС: 10 цифр для юр.лиц, 12 — для индивидуальных предпринимателей.',
    onFail: 'Поле помечается ошибочным, документ получает статус «с предупреждением».' },
  { code: 'date', label: 'Дата',
    check: 'Формат ДД.ММ.ГГГГ или ISO; значение в диапазоне 2000–2030 годов.',
    onFail: 'Поле помечается ошибочным, документ получает статус «с предупреждением».' },
  { code: 'amount_total', label: 'Сумма',
    check: 'Положительное число.',
    onFail: 'Поле помечается ошибочным, документ получает статус «с предупреждением».' },
  { code: 'document', label: 'Тип документа',
    check: 'Должен быть определён классификатором. В тексте должно быть найдено хотя бы одно ключевое поле (ИНН, номер документа или сумма).',
    onFail: 'Документ помечается как «неизвестный тип» и получает статус «с предупреждением».' },
]

const archRows = [
  {
    label: 'Веб-интерфейс',
    items: [
      { name: 'UI', desc: 'То, с чем работает пользователь', tone: 'primary' },
    ],
  },
  {
    label: 'Точки входа',
    items: [
      { name: 'API', desc: 'Точка входа для запросов из веб-интерфейса: вход, поиск, просмотр документов', tone: 'primary' },
      { name: 'Загрузка', desc: 'Приём файлов от пользователя и извлечение текста', tone: 'info' },
    ],
  },
  {
    label: 'Очередь',
    items: [
      { name: 'Очередь сообщений', desc: 'Буфер между загрузкой и обработкой; гарантирует, что ни один файл не потеряется при перезапуске сервисов', tone: 'warning' },
    ],
  },
  {
    label: 'Обработка',
    items: [
      { name: 'Обработка', desc: 'Определение вида, извлечение полей, проверка значений, сохранение в базу', tone: 'info' },
    ],
  },
  {
    label: 'Хранилище',
    items: [
      { name: 'База данных', desc: 'Документы, поля, журнал событий, пользователи; поддерживает полнотекстовый поиск', tone: 'success' },
      { name: 'Файловое хранилище', desc: 'Оригиналы загруженных файлов; повторная загрузка использует уже сохранённый файл', tone: 'secondary' },
    ],
  },
  {
    label: 'Наблюдение',
    items: [
      { name: 'Метрики', desc: 'Числовые показатели работы сервисов: количество загрузок, скорость, размер очереди', tone: 'secondary' },
      { name: 'Сбор логов', desc: 'Логи всех сервисов в одном месте, удобно искать и фильтровать', tone: 'secondary' },
      { name: 'Дашборды', desc: 'Визуализация метрик и просмотр логов в одном интерфейсе', tone: 'secondary' },
    ],
  },
]

const flowSteps = [
  {
    icon: 'mdi-cloud-upload-outline',
    title: 'Загрузка',
    desc: 'Пользователь загружает файл в веб-интерфейс. Файл передаётся в сервис загрузки.',
  },
  {
    icon: 'mdi-text-search',
    title: 'Чтение и проверка дубликата',
    desc: 'Сервис загрузки извлекает текст из файла и считает уникальный отпечаток. Если такой файл уже загружали — возвращается ссылка на существующий документ. Если новый — файл сохраняется на диск, и сообщение об этом ставится в очередь.',
  },
  {
    icon: 'mdi-cog-transfer-outline',
    title: 'Обработка',
    desc: 'Сервис обработки берёт сообщение из очереди, определяет вид документа, извлекает ключевые поля (ИНН, номер, дата, сумма, контрагенты), нормализует и проверяет их, сохраняет результат в базу. Подтверждение чтения снимается с очереди только после успешного сохранения — это гарантирует, что документ не потеряется при сбое.',
  },
  {
    icon: 'mdi-monitor-dashboard',
    title: 'Просмотр и поиск',
    desc: 'Веб-интерфейс получает данные через API: списки документов с фильтрами и поиском, детальный просмотр с журналом обработки, скачивание оригинального файла.',
  },
  {
    icon: 'mdi-content-duplicate',
    title: 'Повторная загрузка',
    desc: 'При попытке загрузить тот же файл система не создаёт дубликат, а возвращает ссылку на оригинал. В интерфейсе видно, что это дубль и в каком состоянии находится оригинал.',
  },
]

// Группируем стадии: «нормальный путь» и «альтернативные финалы».
// Документ при ошибке не идёт после «В БД» — он переходит в один из alt-финалов
// вместо успешного сохранения, поэтому визуально это два раздельных блока.
const flowStages = PIPELINE_STAGES.filter((s) => s.phase === 'flow')
const altStages  = PIPELINE_STAGES.filter((s) => s.phase === 'alt')

onMounted(loadCatalog)

const tocSections = [
  { id: 'doc-types',  label: 'Типы и форматы',          icon: 'mdi-file-document-multiple-outline' },
  { id: 'roles',      label: 'Роли контрагентов',       icon: 'mdi-account-group-outline' },
  { id: 'edge-cases', label: 'Особые случаи',           icon: 'mdi-flask-outline' },
  { id: 'junk',       label: 'Некорректные файлы',      icon: 'mdi-trash-can-outline' },
  { id: 'classifier', label: 'Определение вида',        icon: 'mdi-shape-outline' },
  { id: 'validation', label: 'Проверка полей',          icon: 'mdi-check-circle-outline' },
  { id: 'pipeline',   label: 'Стадии обработки',        icon: 'mdi-timeline-outline' },
  { id: 'arch',       label: 'Архитектура',             icon: 'mdi-graph-outline' },
]
</script>

<template>
  <div class="ref-shell">
    <!-- Left rail TOC (sticky, hidden on narrow) -->
    <aside class="ref-rail">
      <div class="ref-rail-inner">
        <div class="ref-rail-title">На странице</div>
        <a v-for="s in tocSections" :key="s.id" :href="`#${s.id}`" class="ref-rail-link">
          <v-icon size="16" class="ref-rail-icon">{{ s.icon }}</v-icon>
          <span>{{ s.label }}</span>
        </a>
      </div>
    </aside>

    <main class="ref-main">
      <div class="page-header">
        <h1 class="page-title">Справка</h1>
        <p class="page-subtitle">Как устроена система: какие документы поддерживает, как извлекает поля, как обрабатывает ошибочные файлы и из каких компонентов собрана.</p>
      </div>

      <!-- TOC chip-bar для узких экранов (когда rail скрыт) -->
      <div class="toc-chips-only mb-4">
        <a v-for="s in tocSections" :key="s.id" :href="`#${s.id}`" class="toc-link">
          {{ s.label }}
        </a>
      </div>

    <!-- 1. Типы и форматы -->
    <section id="doc-types" class="ref-section">
      <h2 class="ref-section-title">1. Типы документов и поддерживаемые форматы</h2>
      <p class="ref-section-sub">Шесть видов бизнес-документов. У каждого свой набор форматов, в которых шаблон сохраняется без потери информации, и свой потолок по количеству контрагентов.</p>

      <div class="ref-block">
        <v-table density="compact" class="ref-table">
          <thead>
            <tr>
              <th style="width:24%">Тип</th>
              <th style="width:18%; text-align:center">Макс. контрагентов</th>
              <th style="width:24%">Форматы файлов</th>
              <th>Описание</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in docTypeRows" :key="r.type">
              <td><strong>{{ r.label }}</strong></td>
              <td style="text-align:center"><span class="cap-chip">{{ r.cap }}</span></td>
              <td>
                <span v-for="(f, i) in r.formats" :key="f">
                  <code class="fmt-code">{{ f }}</code><span v-if="i < r.formats.length - 1">, </span>
                </span>
              </td>
              <td class="text-caption" style="color: rgb(var(--v-theme-on-surface-variant))">
                <template v-if="r.type === 'invoice'">Счёт-фактура с табличной частью и НДС.</template>
                <template v-else-if="r.type === 'act'">Акт выполненных работ — без позиций, только общая сумма.</template>
                <template v-else-if="r.type === 'contract'">Договор — стороны, предмет, срок действия.</template>
                <template v-else-if="r.type === 'waybill'">Товарная накладная (ТОРГ-12) — таблица позиций.</template>
                <template v-else-if="r.type === 'upd'">Универсальный передаточный документ — гибрид счёта и накладной.</template>
                <template v-else-if="r.type === 'payment_order'">Платёжное поручение — плательщик, получатель, назначение.</template>
              </td>
            </tr>
          </tbody>
        </v-table>
      </div>
      <p class="ref-note">
        <v-icon size="14" class="mr-1">mdi-information-outline</v-icon>
        Жёсткий потолок — <strong>{{ catalog.parties_hard_cap }} контрагента</strong>: больше четырёх ролей в одном реальном бизнес-документе не встречается. Если задать больше, генератор автоматически использует максимум для конкретного типа.
      </p>
    </section>

    <!-- 2. Роли контрагентов -->
    <section id="roles" class="ref-section">
      <h2 class="ref-section-title">2. Роли контрагентов по типам</h2>
      <p class="ref-section-sub">Роли упорядочены от важной к второстепенной. Если выбрано N контрагентов, заполняются первые N ролей таблицы — остальные не появляются в документе.</p>

      <div class="ref-block">
        <v-table density="compact" class="ref-table">
          <thead>
            <tr>
              <th style="width:24%">Тип</th>
              <th style="width:14%; text-align:center">Макс.</th>
              <th>Роли (от важной к второстепенной)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in docTypeRows" :key="r.type">
              <td><strong>{{ r.label }}</strong></td>
              <td style="text-align:center"><span class="cap-chip">{{ r.cap }}</span></td>
              <td>
                <span v-for="(role, i) in r.roles" :key="role" class="role-chip-static">
                  <span class="role-rank-static">{{ i + 1 }}</span>{{ role }}<span v-if="i < r.roles.length - 1" class="role-sep-static">·</span>
                </span>
              </td>
            </tr>
          </tbody>
        </v-table>
      </div>
    </section>

    <!-- 3. Особые случаи -->
    <section id="edge-cases" class="ref-section">
      <h2 class="ref-section-title">3. Особые случаи генерации</h2>
      <p class="ref-section-sub">Тестовые ситуации, на которых проверяется устойчивость извлечения полей. Каждый кейс воспроизводит сложную ситуацию из реальной жизни — обрезанные имена, нестандартный порядок блоков, индивидуальные предприниматели вместо юр.лиц. Используются для оценки качества системы.</p>

      <v-row>
        <v-col v-for="ec in (catalog.edge_cases || [])" :key="ec" cols="12" md="6">
          <div class="ref-block padded">
            <div class="d-flex align-center mb-2" style="gap:10px">
              <v-icon size="22" color="primary">{{ edgeCaseIcon(ec) }}</v-icon>
              <div class="text-subtitle-1" style="font-weight:600">{{ edgeCaseLabel(ec) }}</div>
            </div>
            <div class="text-body-2 mb-3">{{ edgeCaseHint(ec) }}</div>

            <div v-if="ec === 'multiline_names'" class="ec-example">
              <div class="ec-example-label">Пример рендера:</div>
              <pre>Продавец: ООО «Альфа-Бета-
Гамма-Дельта»
ИНН 6613186098, КПП 815901083</pre>
              <div class="ec-bug">→ Простые правила обрежут имя на первой строке и потеряют его вторую часть.</div>
            </div>
            <div v-else-if="ec === 'reordered_blocks'" class="ec-example">
              <div class="ec-example-label">Пример рендера:</div>
              <pre>Грузополучатель: ОАО «Урал»
ИНН 3194875741, КПП 657901754
Грузоотправитель: ИП Михайлов К.Т.
ИНН 219935181990
...
Продавец: ООО «Меридиан»
ИНН 6613186098, КПП 815901083</pre>
              <div class="ec-bug">→ Простые правила определяют роли по порядку появления — здесь это даст зеркальное распределение.</div>
            </div>
            <div v-else-if="ec === 'ip_forms'" class="ec-example">
              <div class="ec-example-label">Режимы интенсивности (задаются в админ-панели):</div>
              <ul class="ec-list">
                <li v-for="m in (catalog.ip_modes || [])" :key="m">
                  <strong>{{ ipModeLabel(m) }}</strong> — {{ ipModeHint(m) }}
                </li>
              </ul>
              <div class="ec-bug">→ Простые правила могут взять КПП от соседнего юр.лица и приписать её предпринимателю, у которого КПП быть не должно.</div>
            </div>
            <div v-else-if="ec === 'missing_optional'" class="ec-example">
              <div class="ec-example-label">Режимы интенсивности (задаются в админ-панели):</div>
              <ul class="ec-list">
                <li v-for="m in (catalog.missing_modes || [])" :key="m">
                  <strong>{{ missingModeLabel(m) }}</strong> — {{ missingModeHint(m) }}
                </li>
              </ul>
              <div class="ec-bug">→ Система должна корректно сохранить пустое значение и не падать на отсутствующих полях.</div>
            </div>
          </div>
        </v-col>
      </v-row>
    </section>

    <!-- 4. Некорректные файлы -->
    <section id="junk" class="ref-section">
      <h2 class="ref-section-title">4. Файлы, не являющиеся документами</h2>
      <p class="ref-section-sub">Тесты для проверки того, как система обрабатывает заведомо некорректные данные. Доступны при генерации тестового набора — выбираются полем «Мусор» в админ-панели.</p>

      <v-row>
        <v-col v-for="(meta, id) in JUNK_KIND_META" :key="id" cols="12" md="6">
          <div class="ref-block padded">
            <div class="d-flex align-center mb-2" style="gap:10px">
              <v-icon size="22" color="warning">{{ meta.icon }}</v-icon>
              <div class="text-subtitle-1" style="font-weight:600">{{ meta.label }}</div>
              <v-chip size="x-small" variant="tonal">{{ meta.ext }}</v-chip>
            </div>
            <div class="text-body-2">{{ meta.hint }}</div>
          </div>
        </v-col>
      </v-row>
    </section>

    <!-- 5. Определение вида документа -->
    <section id="classifier" class="ref-section">
      <h2 class="ref-section-title">5. Определение вида документа</h2>
      <p class="ref-section-sub">Вид документа определяется по характерным фразам в тексте — «Платёжное поручение», «ТОРГ-12», «Универсальный передаточный документ» и т.п. Правила проверяются по очереди, от самых однозначных к более общим. Первое совпадение фиксирует вид. Если ни одно правило не сработало, проверяется имя файла. Если и оно не помогло — вид определить не удалось, документ помечается как «неизвестный тип».</p>

      <div class="ref-block mb-3">
        <v-table density="compact" class="ref-table">
          <thead>
            <tr>
              <th style="width:6%; text-align:center">№</th>
              <th style="width:22%">Тип</th>
              <th>Что ищется в тексте</th>
              <th style="width:34%">Почему именно так</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in classifierRules" :key="r.id">
              <td style="text-align:center"><span class="rule-rank">{{ i + 1 }}</span></td>
              <td><strong>{{ r.label }}</strong></td>
              <td>
                <code v-for="t in r.triggers" :key="t" class="fmt-code d-block mb-1">{{ t }}</code>
              </td>
              <td class="text-caption" style="color: rgb(var(--v-theme-on-surface-variant))">{{ r.note || '—' }}</td>
            </tr>
          </tbody>
        </v-table>
      </div>

      <p class="ref-note">
        <v-icon size="14" class="mr-1">mdi-arrow-right-bold-outline</v-icon>
        <strong>Запасной вариант — по имени файла</strong>. Если правил по тексту не хватило, проверяются токены в имени файла:
      </p>
      <div class="ref-block">
        <v-table density="compact" class="ref-table">
          <thead><tr><th style="width:24%">Тип</th><th>Токены в имени файла</th></tr></thead>
          <tbody>
            <tr v-for="h in filenameHints" :key="h.type">
              <td><strong>{{ formatDocType(h.type) }}</strong></td>
              <td>
                <code v-for="t in h.tokens" :key="t" class="fmt-code mr-2">{{ t }}</code>
              </td>
            </tr>
          </tbody>
        </v-table>
      </div>
    </section>

    <!-- 6. Проверка полей -->
    <section id="validation" class="ref-section">
      <h2 class="ref-section-title">6. Проверка извлечённых полей</h2>
      <p class="ref-section-sub">Каждое извлечённое поле проходит проверку. Если что-то не так, документ всё равно сохраняется, но получает статус «с предупреждением». В деталях документа видно, какое поле проблемное и почему.</p>

      <div class="ref-block">
        <v-table density="compact" class="ref-table">
          <thead>
            <tr>
              <th style="width:18%">Поле</th>
              <th style="width:42%">Что проверяется</th>
              <th>Что произойдёт при ошибке</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="v in validators" :key="v.code">
              <td><strong>{{ v.label }}</strong></td>
              <td class="text-body-2">{{ v.check }}</td>
              <td class="text-body-2">{{ v.onFail }}</td>
            </tr>
          </tbody>
        </v-table>
      </div>
    </section>

    <!-- 7. Стадии обработки -->
    <section id="pipeline" class="ref-section">
      <h2 class="ref-section-title">7. Стадии обработки документа</h2>
      <p class="ref-section-sub">Нормальный путь — последовательное прохождение стадий до сохранения в базу. Если что-то пошло не так на любой стадии, документ попадает в один из альтернативных финалов вместо успешного сохранения. При повторной загрузке того же файла система определяет дубликат и возвращает ссылку на существующий документ.</p>

      <h3 class="ref-subsection-title">Нормальный путь</h3>
      <div class="status-flow">
        <div v-for="(s, i) in flowStages" :key="s.id" class="status-step" :data-color="s.color">
          <div class="status-step-icon">
            <v-icon size="20" :color="s.color">{{ s.icon }}</v-icon>
          </div>
          <div class="status-step-body">
            <div class="status-step-id">{{ s.title }}</div>
            <div class="status-step-desc">{{ s.desc }}</div>
          </div>
          <div v-if="i < flowStages.length - 1" class="status-step-arrow">
            <v-icon size="16">mdi-chevron-down</v-icon>
          </div>
        </div>
      </div>

      <h3 class="ref-subsection-title">Альтернативные финалы</h3>
      <p class="ref-subsection-sub">Достигаются вместо «В БД», если возникла проблема. Это терминальные состояния — последующих стадий нет.</p>
      <div class="status-flow status-flow--alt">
        <div v-for="s in altStages" :key="s.id" class="status-step" :data-color="s.color">
          <div class="status-step-icon">
            <v-icon size="20" :color="s.color">{{ s.icon }}</v-icon>
          </div>
          <div class="status-step-body">
            <div class="status-step-id">{{ s.title }}</div>
            <div class="status-step-desc">{{ s.desc }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 8. Архитектура -->
    <section id="arch" class="ref-section">
      <h2 class="ref-section-title">8. Архитектура и потоки данных</h2>
      <p class="ref-section-sub">Система работает как потоковый конвейер: загруженные файлы проходят несколько независимых стадий и в итоге попадают в базу данных, доступную для поиска и просмотра. Каждая стадия может работать в нескольких экземплярах для увеличения производительности.</p>

      <h3 class="ref-subsection-title">Компоненты системы</h3>
      <div class="arch-stack">
        <div v-for="row in archRows" :key="row.label" class="arch-row">
          <div class="arch-row-label">{{ row.label }}</div>
          <div class="arch-row-items">
            <div v-for="it in row.items" :key="it.name" class="arch-box" :data-tone="it.tone">
              <div class="arch-box-name">{{ it.name }}</div>
              <div class="arch-box-desc">{{ it.desc }}</div>
            </div>
          </div>
        </div>
      </div>

      <h3 class="ref-subsection-title">Используемые технологии</h3>
      <div class="tech-grid">
        <div v-for="t in TECH_STACK" :key="t.component" class="tech-card" :data-tone="t.tone">
          <div class="tech-card-head">
            <div class="tech-card-icon-wrap">
              <v-icon size="22">{{ t.icon }}</v-icon>
            </div>
            <div class="tech-card-component">{{ t.component }}</div>
          </div>
          <div class="tech-card-name">{{ t.tech }}</div>
          <div class="tech-card-detail">{{ t.detail }}</div>
        </div>
      </div>

      <h3 class="ref-subsection-title">Поток обработки документа</h3>
      <div class="flow-steps">
        <div v-for="(step, i) in flowSteps" :key="i" class="flow-step">
          <div class="flow-step-num">{{ i + 1 }}</div>
          <div class="flow-step-body">
            <div class="flow-step-head">
              <v-icon size="18" class="flow-step-icon">{{ step.icon }}</v-icon>
              <span>{{ step.title }}</span>
            </div>
            <div class="flow-step-desc">{{ step.desc }}</div>
          </div>
          <div v-if="i < flowSteps.length - 1" class="flow-step-arrow">
            <v-icon size="18">mdi-chevron-down</v-icon>
          </div>
        </div>
      </div>
    </section>
    </main>
  </div>
</template>

<style scoped>
/* Layout: rail слева, основной контент по центру с capом по ширине.
   Контент шириной ~920px — оптимально для длинных строк текста и таблиц,
   на широких мониторах не растягивается, по бокам остаётся воздух. */
.ref-shell {
  display: grid;
  grid-template-columns: 220px minmax(0, 920px);
  gap: 32px;
  justify-content: center;
  align-items: start;
}

/* Универсальный «блок» — карточный стиль как у app-card в остальных view.
   Без внутреннего padding по умолчанию — для блоков с таблицей (table сам
   управляет своими отступами). Для блоков с обычным контентом — модификатор
   .padded (16px + height:100% для выравнивания карточек в v-row). */
.ref-block {
  border: 1px solid rgb(var(--v-theme-border));
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  overflow: hidden;
}
.ref-block.padded {
  padding: 16px;
  height: 100%;
}
.ref-rail {
  position: sticky;
  /* 60px высота v-app-bar + 16px воздух — иначе rail при скролле уплывает под app-bar */
  top: 76px;
  align-self: start;
  /* Высота равна экрану минус offset, чтобы при длинных списках получить свой scroll */
  max-height: calc(100vh - 96px);
  overflow-y: auto;
}
.ref-rail-inner {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 4px 4px 0;
  /* Без card-фона: rail сливается с background v-main, никаких швов на гуттерах */
}
.ref-rail-title {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.5);
  padding: 4px 10px 8px;
}
.ref-rail-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  border-left: 2px solid transparent;
  text-decoration: none;
  color: rgba(var(--v-theme-on-surface), 0.75);
  font-size: 13px;
  font-weight: 500;
  line-height: 1.3;
  transition: color .12s, border-color .12s;
}
.ref-rail-link:hover {
  color: rgb(var(--v-theme-primary));
  border-left-color: rgba(var(--v-theme-primary), 0.4);
}
.ref-rail-link:hover .ref-rail-icon {
  color: rgb(var(--v-theme-primary));
}
.ref-rail-icon {
  flex-shrink: 0;
  color: rgba(var(--v-theme-on-surface), 0.5);
  transition: color .12s;
}
.ref-main {
  min-width: 0;
}
.toc-chips-only { display: none; }

/* На узких экранах rail прячется, появляется чип-TOC в нормальном потоке */
@media (max-width: 1100px) {
  .ref-shell {
    grid-template-columns: minmax(0, 900px);
    gap: 0;
  }
  .ref-rail { display: none; }
  .toc-chips-only {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 4px 0 8px;
  }
}
.toc-link {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 6px;
  background: rgba(var(--v-theme-primary), 0.08);
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
  font-size: 12.5px;
  font-weight: 500;
  transition: background .12s, color .12s;
}
.toc-link:hover {
  background: rgba(var(--v-theme-primary), 0.18);
}
.ref-section { margin-bottom: 36px; }
.ref-section-title {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -.01em;
  margin: 0 0 6px;
  color: rgb(var(--v-theme-on-background));
}
.ref-section-sub {
  font-size: 13.5px;
  color: rgb(var(--v-theme-on-surface-variant));
  margin: 0 0 16px;
}
.ref-note {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
  margin: 12px 0 16px;
  line-height: 1.55;
}
.ref-note :deep(.v-icon) {
  vertical-align: -2px;
  margin-right: 4px;
}
.ref-subsection-title {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -.005em;
  margin: 24px 0 8px;
  color: rgb(var(--v-theme-on-background));
}
.ref-subsection-sub {
  font-size: 12.5px;
  color: rgb(var(--v-theme-on-surface-variant));
  margin: 0 0 10px;
  line-height: 1.5;
}
/* Tech stack — card-grid с цветными border-left по тонам компонентов,
   тонированные иконки, чип-стиль для технологии. */
.tech-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 720px) {
  .tech-grid { grid-template-columns: 1fr; }
}
.tech-card {
  border: 1px solid rgb(var(--v-theme-border));
  border-left: 3px solid rgb(var(--v-theme-primary));
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  padding: 14px 16px;
  transition: transform .14s ease, border-color .14s ease;
  display: flex;
  flex-direction: column;
}
.tech-card[data-tone="info"]      { border-left-color: rgb(var(--v-theme-info)); }
.tech-card[data-tone="success"]   { border-left-color: rgb(var(--v-theme-success)); }
.tech-card[data-tone="warning"]   { border-left-color: rgb(var(--v-theme-warning)); }
.tech-card[data-tone="secondary"] { border-left-color: rgba(var(--v-theme-on-surface), 0.35); }
.tech-card:hover {
  transform: translateY(-1px);
  border-top-color: rgba(var(--v-theme-primary), 0.4);
  border-right-color: rgba(var(--v-theme-primary), 0.4);
  border-bottom-color: rgba(var(--v-theme-primary), 0.4);
}
.tech-card-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.tech-card-icon-wrap {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  background: rgba(var(--v-theme-primary), 0.14);
  color: rgb(var(--v-theme-primary));
  flex-shrink: 0;
}
.tech-card[data-tone="info"]      .tech-card-icon-wrap { background: rgba(var(--v-theme-info), 0.14);     color: rgb(var(--v-theme-info)); }
.tech-card[data-tone="success"]   .tech-card-icon-wrap { background: rgba(var(--v-theme-success), 0.14);  color: rgb(var(--v-theme-success)); }
.tech-card[data-tone="warning"]   .tech-card-icon-wrap { background: rgba(var(--v-theme-warning), 0.14);  color: rgb(var(--v-theme-warning)); }
.tech-card[data-tone="secondary"] .tech-card-icon-wrap { background: rgba(var(--v-theme-on-surface), 0.08); color: rgba(var(--v-theme-on-surface), 0.65); }
.tech-card-component {
  font-size: 14.5px;
  font-weight: 600;
  letter-spacing: -.005em;
  color: rgb(var(--v-theme-on-surface));
}
.tech-card-name {
  font-family: var(--font-mono);
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface));
  background: rgba(var(--v-theme-on-surface), 0.06);
  padding: 5px 9px;
  border-radius: 6px;
  align-self: flex-start;
  margin-bottom: 8px;
  word-break: break-word;
  line-height: 1.45;
}
.tech-card-detail {
  font-size: 12.5px;
  line-height: 1.5;
  color: rgb(var(--v-theme-on-surface-variant));
}
.ref-table :deep(th),
.ref-table :deep(td) {
  font-size: 0.82rem !important;
  padding: 8px 12px !important;
  border-bottom: 1px solid rgba(var(--v-theme-border), 0.6) !important;
  vertical-align: top;
}
.ref-table :deep(thead th) {
  font-weight: 600;
  letter-spacing: 0.1px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  border-bottom: 1px solid rgb(var(--v-theme-border)) !important;
  text-transform: none;
}
.fmt-code {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  background: rgba(var(--v-theme-on-surface), 0.06);
  padding: 1px 6px;
  border-radius: 4px;
}
.cap-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 0.78rem;
  background: rgba(var(--v-theme-primary), 0.14);
  color: rgb(var(--v-theme-primary));
  font-variant-numeric: tabular-nums;
}
.role-chip-static {
  display: inline-flex;
  align-items: center;
  font-size: 0.8rem;
}
.role-rank-static {
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
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-variant-numeric: tabular-nums;
}
.role-sep-static {
  display: inline-block;
  margin: 0 6px;
  color: rgba(var(--v-theme-on-surface), 0.25);
}
.rule-rank {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: rgba(var(--v-theme-primary), 0.16);
  color: rgb(var(--v-theme-primary));
  font-weight: 700;
  font-size: 0.75rem;
  font-variant-numeric: tabular-nums;
}

.ec-example {
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid rgb(var(--v-theme-border));
  border-radius: 8px;
  background: rgb(var(--v-theme-surface-variant));
  font-size: 12.5px;
}
.ec-example-label {
  font-size: 11.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .04em;
  color: rgba(var(--v-theme-on-surface), 0.55);
  margin-bottom: 4px;
}
.ec-example pre {
  font-family: var(--font-mono);
  font-size: 11.5px;
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.5;
}
.ec-list {
  list-style: disc;
  padding-left: 18px;
  margin: 4px 0;
  font-size: 12.5px;
  line-height: 1.6;
}
.ec-bug {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed rgba(var(--v-theme-warning), 0.5);
  color: rgb(var(--v-theme-warning));
  font-size: 12px;
  line-height: 1.45;
}

/* Pipeline status flow */
.status-flow {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.status-step {
  display: grid;
  grid-template-columns: 36px 1fr;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border: 1px solid rgb(var(--v-theme-border));
  border-radius: 10px;
  background: rgb(var(--v-theme-surface));
  margin-bottom: 6px;
  position: relative;
}
.status-step-icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: rgba(var(--v-theme-on-surface), 0.05);
}
.status-step[data-color="success"] .status-step-icon { background: rgba(var(--v-theme-success), 0.14); }
.status-step[data-color="warning"] .status-step-icon { background: rgba(var(--v-theme-warning), 0.14); }
.status-step[data-color="error"]   .status-step-icon { background: rgba(var(--v-theme-error), 0.14); }
.status-step[data-color="info"]    .status-step-icon { background: rgba(var(--v-theme-info), 0.14); }
.status-step-id {
  font-size: 14px;
  font-weight: 600;
  display: inline-block;
  margin-bottom: 4px;
  letter-spacing: -.005em;
}
.status-step-desc {
  font-size: 13px;
  line-height: 1.55;
  color: rgb(var(--v-theme-on-surface));
}
.status-step-arrow {
  position: absolute;
  bottom: -14px;
  left: 30px;
  width: 16px;
  text-align: center;
  color: rgba(var(--v-theme-on-surface), 0.3);
  z-index: 1;
}

/* Architecture */
.arch-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.arch-row {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 14px;
  align-items: center;
}
.arch-row-label {
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.55);
  text-align: right;
  padding-right: 4px;
  border-right: 2px solid rgba(var(--v-theme-border), 0.7);
}
.arch-row-items {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.arch-box {
  flex: 0 1 auto;
  min-width: 200px;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid rgb(var(--v-theme-border));
  background: rgb(var(--v-theme-surface));
  transition: transform .12s, border-color .12s;
}
.arch-box:hover {
  transform: translateY(-1px);
  border-color: rgba(var(--v-theme-primary), 0.5);
}
.arch-box[data-tone="primary"]   { border-left: 3px solid rgb(var(--v-theme-primary)); }
.arch-box[data-tone="info"]      { border-left: 3px solid rgb(var(--v-theme-info)); }
.arch-box[data-tone="success"]   { border-left: 3px solid rgb(var(--v-theme-success)); }
.arch-box[data-tone="warning"]   { border-left: 3px solid rgb(var(--v-theme-warning)); }
.arch-box[data-tone="secondary"] { border-left: 3px solid rgba(var(--v-theme-on-surface), 0.25); }
.arch-box-name {
  font-size: 13.5px;
  font-weight: 600;
  margin-bottom: 2px;
}
.arch-box-desc {
  font-size: 12px;
  line-height: 1.4;
  color: rgb(var(--v-theme-on-surface-variant));
}
/* Поток обработки — визуальный пошаговый блок (не плоский список).
   Структура аналогична .status-step, но вместо иконки слева — номер шага,
   а сам заголовок шага содержит тематическую иконку. */
.flow-steps {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.flow-step {
  display: grid;
  grid-template-columns: 36px 1fr;
  align-items: flex-start;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid rgb(var(--v-theme-border));
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  margin-bottom: 8px;
  position: relative;
}
.flow-step-num {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: rgba(var(--v-theme-primary), 0.16);
  color: rgb(var(--v-theme-primary));
  font-weight: 700;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}
.flow-step-body {
  min-width: 0;
}
.flow-step-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 4px;
  letter-spacing: -.005em;
}
.flow-step-icon {
  flex-shrink: 0;
  color: rgb(var(--v-theme-primary));
  opacity: .85;
}
.flow-step-desc {
  font-size: 13px;
  line-height: 1.55;
  color: rgb(var(--v-theme-on-surface));
}
.flow-step-arrow {
  position: absolute;
  bottom: -14px;
  left: 28px;
  width: 18px;
  text-align: center;
  color: rgba(var(--v-theme-on-surface), 0.35);
  background: rgb(var(--v-theme-background));
  border-radius: 50%;
  z-index: 1;
}

@media (max-width: 720px) {
  .arch-row { grid-template-columns: 1fr; }
  .arch-row-label {
    text-align: left;
    border-right: none;
    border-bottom: 2px solid rgba(var(--v-theme-border), 0.7);
    padding-right: 0;
    padding-bottom: 4px;
  }
}
</style>
