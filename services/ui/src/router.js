import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth.js'

import LoginView from './views/LoginView.vue'
import UploadView from './views/UploadView.vue'
import DocumentsView from './views/DocumentsView.vue'
import DocumentDetailView from './views/DocumentDetailView.vue'
import AdminView from './views/AdminView.vue'
import ProfileView from './views/ProfileView.vue'
import ReferenceView from './views/ReferenceView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView, meta: { public: true } },
    { path: '/', redirect: '/documents' },
    { path: '/upload', component: UploadView },
    { path: '/documents', component: DocumentsView },
    { path: '/documents/:id', component: DocumentDetailView, props: true },
    { path: '/admin', component: AdminView },
    { path: '/reference', component: ReferenceView },
    { path: '/profile', component: ProfileView },
  ]
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isAuthenticated) {
    return { path: '/login', query: { next: to.fullPath } }
  }
})

export default router
