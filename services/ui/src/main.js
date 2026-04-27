import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import './styles/app.scss'

import App from './App.vue'
import router from './router.js'

const lightTheme = {
  dark: false,
  colors: {
    primary: '#4F46E5',
    'primary-darken-1': '#4338CA',
    secondary: '#64748B',
    success: '#059669',
    warning: '#D97706',
    error: '#DC2626',
    info: '#0E7490',
    background: '#F6F8FB',
    surface: '#FFFFFF',
    'surface-bright': '#FFFFFF',
    'surface-light': '#F8FAFC',
    'surface-variant': '#F1F5F9',
    'on-background': '#0F172A',
    'on-surface': '#0F172A',
    'on-surface-variant': '#475569',
    'on-primary': '#FFFFFF',
    border: '#E5E7EB',
  },
}

const darkTheme = {
  dark: true,
  colors: {
    primary: '#818CF8',
    'primary-darken-1': '#6366F1',
    secondary: '#94A3B8',
    success: '#34D399',
    warning: '#FBBF24',
    error: '#F87171',
    info: '#22D3EE',
    background: '#0B1220',
    surface: '#111A2E',
    'surface-bright': '#1B2540',
    'surface-light': '#1B2540',
    'surface-variant': '#1B2540',
    'on-background': '#E2E8F0',
    'on-surface': '#E2E8F0',
    'on-surface-variant': '#94A3B8',
    'on-primary': '#0B1220',
    border: '#1E293B',
  },
}

const vuetify = createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: localStorage.getItem('theme') || 'light',
    themes: { light: lightTheme, dark: darkTheme },
  },
  defaults: {
    VCard: { rounded: 'lg', elevation: 0 },
    VBtn: { rounded: 'lg', flat: true, style: 'text-transform: none; letter-spacing: 0;' },
    VTextField: { variant: 'outlined', density: 'comfortable', color: 'primary', rounded: 'lg' },
    VSelect: { variant: 'outlined', density: 'comfortable', color: 'primary', rounded: 'lg' },
    VAutocomplete: { variant: 'outlined', density: 'comfortable', color: 'primary', rounded: 'lg' },
    VCombobox: { variant: 'outlined', density: 'comfortable', color: 'primary', rounded: 'lg' },
    VTextarea: { variant: 'outlined', density: 'comfortable', color: 'primary', rounded: 'lg' },
    VChip: { rounded: 'md' },
    VAlert: { rounded: 'lg', variant: 'tonal' },
    VDialog: { transition: 'dialog-bottom-transition' },
  },
})

createApp(App).use(createPinia()).use(router).use(vuetify).mount('#app')
