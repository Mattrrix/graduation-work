<script setup>
import { ref, computed, onMounted } from 'vue'
import { useTheme } from 'vuetify'
import { useAuthStore } from './stores/auth.js'
import { useRouter, useRoute } from 'vue-router'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const theme = useTheme()
const drawer = ref(true)

const navItems = [
  { to: '/documents', icon: 'mdi-file-document-multiple-outline', title: 'Документы' },
  { to: '/upload', icon: 'mdi-cloud-upload-outline', title: 'Загрузка' },
  { to: '/admin', icon: 'mdi-cog-outline', title: 'Админ-панель' },
  { to: '/reference', icon: 'mdi-book-open-variant-outline', title: 'Справка' },
]

const pageTitle = computed(() => {
  if (route.path.startsWith('/documents/') && route.path !== '/documents') return 'Документ'
  if (route.path === '/profile') return 'Профиль'
  return navItems.find((n) => route.path.startsWith(n.to))?.title || ''
})

const isDark = computed(() => theme.global.current.value.dark)
const isPublic = computed(() => route.meta?.public)

function logout() {
  auth.logout()
  router.push('/login')
}

function toggleTheme() {
  const next = isDark.value ? 'light' : 'dark'
  theme.global.name.value = next
  localStorage.setItem('theme', next)
}

onMounted(() => {
  if (auth.isAuthenticated) auth.fetchProfile()
})
</script>

<template>
  <v-app>
    <template v-if="auth.isAuthenticated && !isPublic">
      <v-navigation-drawer v-model="drawer" :width="252" color="surface" border="end">
        <div class="px-5 py-5 brand">
          <div class="brand-logo" aria-label="ETL Pipeline">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
              <rect x="5"  y="5"    width="14" height="3" rx="1.4" fill="currentColor"/>
              <rect x="5"  y="10.5" width="10" height="3" rx="1.4" fill="currentColor" opacity=".82"/>
              <rect x="5"  y="16"   width="14" height="3" rx="1.4" fill="currentColor" opacity=".64"/>
              <circle cx="20.4" cy="6.5"  r="1.2" fill="#FDE68A"/>
              <circle cx="16.4" cy="12"   r="1.2" fill="#FCA5A5"/>
              <circle cx="20.4" cy="17.5" r="1.2" fill="#86EFAC"/>
            </svg>
          </div>
          <div style="font-weight:600;font-size:15px;line-height:1">ETL Pipeline</div>
        </div>
        <v-divider />

        <v-list nav density="comfortable" class="pa-3">
          <v-list-item
            v-for="item in navItems"
            :key="item.to"
            :to="item.to"
            :prepend-icon="item.icon"
            :title="item.title"
            rounded="lg"
            color="primary"
            class="mb-1"
          />
        </v-list>

        <template #append>
          <v-divider />
          <div class="pa-3">
            <router-link to="/profile" class="user-card">
              <v-avatar color="primary" size="36" class="user-card-avatar">
                <span style="color:white;font-weight:600;font-size:13px;letter-spacing:-.01em">{{ auth.initials }}</span>
              </v-avatar>
              <div class="user-card-text">
                <div class="user-card-name">{{ auth.displayName }}</div>
                <div class="user-card-email" :title="auth.email || auth.username">
                  {{ auth.email || auth.username }}
                </div>
              </div>
            </router-link>

            <v-btn
              block
              variant="tonal"
              size="small"
              :prepend-icon="isDark ? 'mdi-weather-sunny' : 'mdi-weather-night'"
              class="justify-start mb-1"
              @click="toggleTheme"
            >
              {{ isDark ? 'Светлая тема' : 'Тёмная тема' }}
            </v-btn>
            <v-btn
              block
              variant="text"
              size="small"
              prepend-icon="mdi-logout"
              color="error"
              class="justify-start"
              @click="logout"
            >
              Выйти
            </v-btn>
          </div>
        </template>
      </v-navigation-drawer>

      <v-app-bar flat color="background" :elevation="0" border="bottom" height="60">
        <v-app-bar-nav-icon variant="text" @click="drawer = !drawer" />
        <v-app-bar-title style="font-weight:600;font-size:15px">{{ pageTitle }}</v-app-bar-title>
        <template #append>
          <v-btn
            icon
            variant="text"
            size="small"
            :title="isDark ? 'Светлая тема' : 'Тёмная тема'"
            @click="toggleTheme"
          >
            <v-icon>{{ isDark ? 'mdi-weather-sunny' : 'mdi-weather-night' }}</v-icon>
          </v-btn>
        </template>
      </v-app-bar>
    </template>

    <v-main>
      <router-view v-if="isPublic" />
      <v-container v-else fluid class="pa-6">
        <router-view />
      </v-container>
    </v-main>
  </v-app>
</template>
