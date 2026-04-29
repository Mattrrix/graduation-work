import axios from 'axios'

const BASE = import.meta.env.VITE_API_BASE || '/api'

const client = axios.create({ baseURL: BASE })

let refreshPromise = null

function clearTokens() {
  localStorage.removeItem('token')
  localStorage.removeItem('refresh_token')
}

async function refreshAccessToken() {
  if (refreshPromise) return refreshPromise
  const rtoken = localStorage.getItem('refresh_token')
  if (!rtoken) return Promise.reject(new Error('no refresh token'))

  refreshPromise = axios
    .post(`${BASE}/auth/refresh`, { refresh_token: rtoken })
    .then(({ data }) => {
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      return data.access_token
    })
    .finally(() => {
      refreshPromise = null
    })

  return refreshPromise
}

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  (r) => r,
  async (err) => {
    const original = err.config
    const status = err.response?.status
    const isRefreshCall = original?.url?.includes('/auth/refresh')

    if (status === 401 && original && !original._retry && !isRefreshCall) {
      original._retry = true
      try {
        const newToken = await refreshAccessToken()
        original.headers.Authorization = `Bearer ${newToken}`
        return client(original)
      } catch {
        clearTokens()
        if (location.pathname !== '/login') location.href = '/login'
        return Promise.reject(err)
      }
    }

    if (status === 401) {
      clearTokens()
      if (location.pathname !== '/login') location.href = '/login'
    }

    return Promise.reject(err)
  }
)

export default client
