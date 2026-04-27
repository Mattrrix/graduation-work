<script setup>
import { ref } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { useRouter, useRoute } from 'vue-router'

const username = ref('admin')
const password = ref('admin')
const error = ref('')
const loading = ref(false)
const showPassword = ref(false)

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    router.push(route.query.next || '/documents')
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-shell">
    <div class="login-form-side">
      <div style="width:100%;max-width:380px">
        <div class="brand mb-10">
          <div class="brand-logo">E</div>
          <div style="font-weight:600;font-size:17px">ETL Pipeline</div>
        </div>

        <h1 class="page-title mb-2">С возвращением</h1>
        <p class="page-subtitle mb-8">Войдите, чтобы управлять документами</p>

        <v-form @submit.prevent="submit">
          <v-text-field
            v-model="username"
            label="Логин"
            prepend-inner-icon="mdi-account-outline"
            autofocus
            class="mb-3"
          />
          <v-text-field
            v-model="password"
            label="Пароль"
            :type="showPassword ? 'text' : 'password'"
            prepend-inner-icon="mdi-lock-outline"
            :append-inner-icon="showPassword ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
            @click:append-inner="showPassword = !showPassword"
            @keyup.enter="submit"
          />

          <v-alert v-if="error" type="error" density="compact" class="mt-3">{{ error }}</v-alert>

          <v-btn
            type="submit"
            color="primary"
            size="large"
            block
            :loading="loading"
            class="mt-5"
          >
            Войти
            <template #append>
              <v-icon>mdi-arrow-right</v-icon>
            </template>
          </v-btn>
        </v-form>

        <p class="text-caption text-medium-emphasis mt-8 text-center">
          ВКР МАИ · 2026 · Дипломная работа
        </p>
      </div>
    </div>

    <div class="login-hero">
      <div class="brand">
        <div class="brand-logo" style="background: rgba(255,255,255,.18); box-shadow: none">E</div>
        <div style="font-weight:600;font-size:17px;color:white">ETL Pipeline</div>
      </div>

      <div style="max-width:480px">
        <h2>Поточная обработка<br>русскоязычных документов</h2>
        <p>
          Kafka → парсинг → AI-extract → Postgres → веб-интерфейс с поиском.
          Идемпотентный pipeline, дашборды Grafana, HITL-разметка извлечённых полей.
        </p>
      </div>

      <div class="hero-stats">
        <div>
          <div class="num">8</div>
          <div>контейнеров</div>
        </div>
        <div>
          <div class="num">10</div>
          <div>панелей</div>
        </div>
        <div>
          <div class="num">6</div>
          <div>типов документов</div>
        </div>
      </div>
    </div>
  </div>
</template>
