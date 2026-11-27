import { createRouter, createWebHistory } from 'vue-router'

import Overview from '@/views/Overview.vue'
import SignoffReverifyView from '@/views/SignoffReverifyView.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    // 固定路径必须排在动态模块路径之前，避免被 /:moduleKey 抢先匹配。
    { path: '/signoff_reverify', name: 'signoff_reverify', component: SignoffReverifyView },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
