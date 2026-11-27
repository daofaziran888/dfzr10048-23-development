<template>
  <section class="page reverify-page" data-testid="reverify-page">
    <header class="page-head">
      <div>
        <h2>签收正文复验</h2>
        <p class="page-desc">
          按历史包号提交签收摘要与手中字幕，服务端计算实际校验。已签收的包只按签收当时的
          V1 正文验证，V2 及后续版本不参与判断；复验通过才补成正式引用，凭据永久归档。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" data-testid="refresh" type="button" :disabled="loading" @click="refreshAll">
          {{ loading ? '刷新中…' : '刷新复验状态' }}
        </button>
      </div>
    </header>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">历史签收包</span>
        <strong class="stat-value" data-testid="stat-total">{{ status.total }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">已补成正式引用</span>
        <strong class="stat-value" data-testid="stat-confirmed">{{ status.confirmed }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">引用未确认</span>
        <strong class="stat-value" data-testid="stat-unconfirmed">{{ status.unconfirmed }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">归档凭据</span>
        <strong class="stat-value" data-testid="stat-credentials">{{ status.credentials }}</strong>
      </article>
    </div>

    <table class="data-table reverify-packs">
      <thead>
        <tr>
          <th>包号</th><th>接收人</th><th>签收日期</th><th>签收版本</th>
          <th>原签收摘要</th><th>复验结论</th><th>正式引用</th><th>真实引用数</th><th>还需办理</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="pack in packs"
          :key="pack.pack_id"
          :data-testid="`pack-${pack.pack_id}`"
          :data-confirmed="pack.reference_confirmed ? 'true' : 'false'"
          :class="{ selected: form.pack_id === pack.pack_id }"
        >
          <td>
            <button class="link" type="button" :data-testid="`select-${pack.pack_id}`" @click="selectPack(pack)">
              {{ pack.pack_id }}
            </button>
          </td>
          <td>{{ pack.receiver }}</td>
          <td>{{ pack.signed_at }}</td>
          <td>{{ pack.version_no }}</td>
          <td class="mono">{{ pack.signoff_digest }}</td>
          <td>{{ pack.verdict }}</td>
          <td :data-testid="`formal-${pack.pack_id}`">
            {{ pack.reference_confirmed ? pack.reference_id : '无' }}
          </td>
          <td :data-testid="`refcount-${pack.pack_id}`">{{ pack.real_ref_count }}</td>
          <td :data-testid="`handler-${pack.pack_id}`">{{ pack.needs_handler ? pack.next_handler : '无需办理' }}</td>
        </tr>
        <tr v-if="!packs.length">
          <td colspan="9" class="empty-state">暂无历史签收包</td>
        </tr>
      </tbody>
    </table>

    <form class="reverify-form" data-testid="reverify-form" @submit.prevent="submit">
      <h3>提交复验</h3>
      <label class="reverify-field">
        <span>字幕包号</span>
        <input
          v-model="form.pack_id"
          data-testid="reverify-pack"
          placeholder="例如 SBPK-0004"
          list="reverify-pack-options"
          required
        />
        <datalist id="reverify-pack-options">
          <option v-for="pack in packs" :key="pack.pack_id" :value="pack.pack_id" />
        </datalist>
      </label>
      <label class="reverify-field">
        <span>签收摘要</span>
        <input
          v-model="form.signoff_digest"
          data-testid="reverify-digest"
          placeholder="签收当时记录的原摘要"
          required
        />
      </label>
      <label class="reverify-field">
        <span>手中字幕</span>
        <textarea
          v-model="form.subtitles"
          data-testid="reverify-subtitles"
          rows="6"
          placeholder="粘贴接收人手中的字幕正文"
          required
        />
      </label>
      <label class="reverify-field">
        <span>提交人</span>
        <input v-model="form.operator" data-testid="reverify-operator" placeholder="接收人标识（可选）" />
      </label>
      <div class="page-actions reverify-actions">
        <button class="btn primary" data-testid="submit-reverify" type="submit" :disabled="submitting">
          {{ submitting ? '复验中…' : '提交复验' }}
        </button>
        <span v-if="errorMessage" class="error-text" data-testid="reverify-error">{{ errorMessage }}</span>
      </div>
    </form>

    <section v-if="result" class="reverify-result" data-testid="reverify-result">
      <h3>
        复验结论：
        <span :class="result.ok ? 'verdict-pass' : 'verdict-fail'" data-testid="result-verdict">
          {{ result.verdict }}
        </span>
      </h3>
      <p data-testid="result-message">{{ result.message }}</p>
      <dl class="reverify-checks">
        <div><dt>提交摘要</dt><dd class="mono" data-testid="check-submitted">{{ result.checks.submitted_digest || '—' }}</dd></div>
        <div><dt>实际摘要</dt><dd class="mono" data-testid="check-computed">{{ result.checks.computed_digest || '—' }}</dd></div>
        <div><dt>V1 归档摘要</dt><dd class="mono" data-testid="check-archived">{{ result.checks.archived_digest || '—' }}</dd></div>
        <div>
          <dt>本次是否补成正式引用</dt>
          <dd data-testid="result-became-formal">{{ result.became_formal_reference ? '是' : '否' }}</dd>
        </div>
        <div><dt>引用状态</dt><dd data-testid="result-refstate">{{ result.reference_state }}</dd></div>
        <div><dt>正式引用编号</dt><dd data-testid="result-refid">{{ result.reference_id || '无' }}</dd></div>
        <div><dt>真实引用数</dt><dd data-testid="result-refcount">{{ result.real_ref_count }}</dd></div>
        <div>
          <dt>还需谁办理</dt>
          <dd data-testid="result-handler">{{ result.needs_handler ? result.next_handler : '无需办理' }}</dd>
        </div>
      </dl>
      <p v-if="result.notes.length" class="reverify-note" data-testid="result-notes">
        {{ result.notes.join('；') }}
      </p>
    </section>

    <section class="reverify-credentials">
      <h3>归档凭据（永久保存）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>凭据编号</th><th>包号</th><th>结论</th><th>实际摘要</th>
            <th>正式引用</th><th>真实引用数</th><th>提交人</th><th>复验时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in credentials" :key="item.credential_id" :data-testid="`cred-${item.credential_id}`">
            <td class="mono">{{ item.credential_id }}</td>
            <td>{{ item.pack_id }}</td>
            <td :class="item.verdict === '通过' ? 'verdict-pass' : 'verdict-fail'">{{ item.verdict }}</td>
            <td class="mono">{{ item.computed_digest || '—' }}</td>
            <td>{{ item.reference_id || '无' }}</td>
            <td>{{ item.real_ref_count }}</td>
            <td>{{ item.operator }}</td>
            <td>{{ item.created_at }}</td>
          </tr>
          <tr v-if="!credentials.length">
            <td colspan="8" class="empty-state">暂无归档凭据，尚未进行复验</td>
          </tr>
        </tbody>
      </table>
    </section>

    <footer class="page-foot">
      <span>复验只认签收当时的 V1 正文与历史签收摘要，未确认引用不计入真实引用数</span>
      <span v-if="pageMessage" :class="pageMessageKind === 'error' ? 'error-text' : 'ok-text'">{{ pageMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import {
  listReverifyCredentials,
  listReverifyPacks,
  loadReverifyStatus,
  submitReverify,
} from '@/api/backend-service'
import type {
  ReverifyCredential,
  ReverifyPack,
  ReverifyResult,
  ReverifyStatus,
} from '@/api/backend-service'

const packs = ref<ReverifyPack[]>([])
const credentials = ref<ReverifyCredential[]>([])
const status = ref<ReverifyStatus>({ total: 0, confirmed: 0, unconfirmed: 0, credentials: 0 })
const loading = ref(false)
const submitting = ref(false)
const errorMessage = ref('')
const pageMessage = ref('')
const pageMessageKind = ref<'ok' | 'error'>('ok')
const result = ref<ReverifyResult | null>(null)

const form = reactive({
  pack_id: '',
  signoff_digest: '',
  subtitles: '',
  operator: '',
})

function selectPack(pack: ReverifyPack) {
  form.pack_id = pack.pack_id
  form.signoff_digest = pack.signoff_digest
  pageMessage.value = ''
  pageMessageKind.value = 'ok'
}

async function refreshAll() {
  loading.value = true
  try {
    const [packList, credentialList, statusPayload] = await Promise.all([
      listReverifyPacks(),
      listReverifyCredentials(),
      loadReverifyStatus(),
    ])
    packs.value = packList
    credentials.value = credentialList
    status.value = statusPayload
  } catch (error) {
    pageMessage.value = error instanceof Error ? error.message : '复验状态刷新失败'
    pageMessageKind.value = 'error'
  } finally {
    loading.value = false
  }
}

async function submit() {
  submitting.value = true
  errorMessage.value = ''
  pageMessage.value = ''
  try {
    result.value = await submitReverify({ ...form })
    pageMessageKind.value = result.value.ok ? 'ok' : 'error'
    pageMessage.value = result.value.ok ? '复验通过，正式引用已补全' : '复验未通过，引用仍未确认'
    await refreshAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '复验提交失败'
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  await refreshAll()
  if (packs.value.length) selectPack(packs.value[0])
})
</script>

<style scoped>
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.reverify-packs tr.selected { background: #eef4ff; }
.reverify-form { margin: 16px 0; padding: 14px; background: #fff; border: 1px solid var(--border); border-radius: 8px; }
.reverify-form h3 { margin: 0 0 10px; font-size: 15px; }
.reverify-field { display: block; margin-bottom: 10px; }
.reverify-field span { display: block; color: var(--muted); font-size: 12px; margin-bottom: 4px; }
.reverify-field input, .reverify-field textarea {
  width: 100%; border: 1px solid var(--border); border-radius: 6px; padding: 8px;
  font-family: inherit; font-size: 13px;
}
.reverify-actions { align-items: center; }
.reverify-result { margin: 16px 0; padding: 14px; background: #fff; border: 1px solid var(--border); border-radius: 8px; }
.reverify-result h3 { margin: 0 0 8px; font-size: 15px; }
.reverify-checks { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 12px 0 0; }
.reverify-checks dt { color: var(--muted); font-size: 12px; margin-bottom: 2px; }
.reverify-checks dd { margin: 0; font-size: 13px; word-break: break-all; }
.reverify-note { color: var(--muted); font-size: 12px; margin: 10px 0 0; }
.verdict-pass { color: #15803d; font-weight: 600; }
.verdict-fail { color: #b42318; font-weight: 600; }
.ok-text { color: #15803d; }
.reverify-credentials { margin-top: 16px; }
.reverify-credentials h3 { margin: 0 0 8px; font-size: 15px; }
</style>
