<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth.js'

const auth = useAuthStore()
const firstName = ref('')
const lastName = ref('')
const email = ref('')
const saving = ref(false)
const error = ref('')
const snack = ref({ show: false, text: '', color: 'success' })

function syncFromStore() {
  firstName.value = auth.profile.first_name || ''
  lastName.value = auth.profile.last_name || ''
  email.value = auth.profile.email || ''
}

async function save() {
  error.value = ''
  saving.value = true
  try {
    await auth.updateProfile({
      first_name: firstName.value,
      last_name: lastName.value,
      email: email.value,
    })
    snack.value = { show: true, text: 'Профиль сохранён', color: 'success' }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await auth.fetchProfile()
  syncFromStore()
})
</script>

<template>
  <div>
    <div class="page-header">
      <h1 class="page-title">Профиль</h1>
      <p class="page-subtitle">Личные данные и контактная информация</p>
    </div>

    <v-row>
      <v-col cols="12" md="4">
        <v-card class="app-card" style="height:100%">
          <v-card-text class="pa-6 text-center">
            <v-avatar color="primary" size="96" class="mb-4">
              <span style="color:white;font-weight:600;font-size:34px;letter-spacing:-.02em">{{ auth.initials }}</span>
            </v-avatar>
            <div class="text-h6" style="font-weight:600">{{ auth.displayName }}</div>
            <div class="text-body-2 text-medium-emphasis mt-1">{{ auth.email || '—' }}</div>
            <v-divider class="my-5" />
            <div class="info-row">
              <div class="info-row-label">Логин</div>
              <div class="info-row-value mono">{{ auth.username }}</div>
            </div>
            <div class="info-row">
              <div class="info-row-label">Роль</div>
              <div class="info-row-value">
                <v-chip size="small" variant="tonal" color="primary">{{ auth.role }}</v-chip>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="8">
        <v-card class="app-card">
          <v-card-text class="pa-6">
            <div class="text-subtitle-1 mb-1" style="font-weight:600">Личные данные</div>
            <div class="text-body-2 text-medium-emphasis mb-5">
              Имя и фамилия отображаются в боковой панели. Email используется для связи.
            </div>

            <v-form @submit.prevent="save">
              <v-row dense>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="firstName"
                    label="Имя"
                    prepend-inner-icon="mdi-account-outline"
                    placeholder="Иван"
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="lastName"
                    label="Фамилия"
                    placeholder="Иванов"
                  />
                </v-col>
              </v-row>

              <v-text-field
                v-model="email"
                label="Email"
                type="email"
                prepend-inner-icon="mdi-email-outline"
                placeholder="ivan@example.com"
                hint="Формат: name@domain.tld"
              />

              <v-alert v-if="error" type="error" density="compact" class="mt-2">{{ error }}</v-alert>

              <div class="mt-5 d-flex" style="gap:8px">
                <v-btn color="primary" type="submit" :loading="saving" prepend-icon="mdi-content-save-outline">
                  Сохранить
                </v-btn>
                <v-btn variant="text" @click="syncFromStore">Сбросить</v-btn>
              </div>
            </v-form>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3000" location="top right">
      {{ snack.text }}
    </v-snackbar>
  </div>
</template>
