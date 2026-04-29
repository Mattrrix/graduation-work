import { defineStore } from 'pinia'
import client from '../api/client.js'

const STORAGE_KEY = 'profile'

function loadProfile() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function persistProfile(p) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(p))
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    refreshToken: localStorage.getItem('refresh_token') || '',
    username: localStorage.getItem('username') || '',
    role: localStorage.getItem('role') || '',
    profile: loadProfile(),
  }),
  getters: {
    isAuthenticated: (s) => !!s.token,
    displayName: (s) => {
      const fn = s.profile.first_name || ''
      const ln = s.profile.last_name || ''
      const full = `${fn} ${ln}`.trim()
      return full || s.username || '—'
    },
    email: (s) => s.profile.email || '',
    initials: (s) => {
      const fn = s.profile.first_name || ''
      const ln = s.profile.last_name || ''
      if (fn || ln) return ((fn[0] || '') + (ln[0] || '')).toUpperCase() || '?'
      return (s.username || '?')[0].toUpperCase()
    },
  },
  actions: {
    async login(username, password) {
      const form = new URLSearchParams()
      form.append('username', username)
      form.append('password', password)
      const { data } = await client.post('/auth/login', form, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      this.token = data.access_token
      this.refreshToken = data.refresh_token
      this.role = data.role
      this.username = data.username || username
      localStorage.setItem('token', this.token)
      localStorage.setItem('refresh_token', this.refreshToken)
      localStorage.setItem('role', this.role)
      localStorage.setItem('username', this.username)
      await this.fetchProfile()
    },

    async fetchProfile() {
      try {
        const { data } = await client.get('/auth/me')
        this.profile = {
          first_name: data.first_name || '',
          last_name: data.last_name || '',
          email: data.email || '',
        }
        this.username = data.username
        this.role = data.role
        localStorage.setItem('username', this.username)
        localStorage.setItem('role', this.role)
        persistProfile(this.profile)
      } catch {}
    },

    async updateProfile(payload) {
      const { data } = await client.patch('/auth/me', payload)
      this.profile = {
        first_name: data.first_name || '',
        last_name: data.last_name || '',
        email: data.email || '',
      }
      persistProfile(this.profile)
      return data
    },

    async logout() {
      const refresh = this.refreshToken || localStorage.getItem('refresh_token') || ''
      try {
        await client.post('/auth/logout', { refresh_token: refresh })
      } catch {}
      this.token = ''
      this.refreshToken = ''
      this.role = ''
      this.username = ''
      this.profile = {}
      localStorage.removeItem('token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('role')
      localStorage.removeItem('username')
      localStorage.removeItem(STORAGE_KEY)
    },
  },
})
