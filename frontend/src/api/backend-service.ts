import { request } from './client'
import { moduleMeta } from '@/data/modules'
import type { ActionResult, EntryRow, OverviewResult, PageResult } from '@/data/types'

export { moduleMeta }

export async function listEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<PageResult> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}?${query}`)
  if (!response.ok) throw new Error('业务数据读取失败')
  return await response.json()
}

export async function createEntry(
  key: string,
  values: Record<string, string>,
): Promise<ActionResult> {
  const response = await request(`/api/${key}`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  return await response.json()
}

export async function runAction(
  key: string,
  id: number,
  action: string,
): Promise<ActionResult> {
  const response = await request(`/api/${key}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
  return await response.json()
}

export async function downloadEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<void> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}/export?${query}`)
  if (!response.ok) throw new Error('业务数据导出失败')
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${key}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export async function loadOverview(): Promise<OverviewResult> {
  const response = await request('/api/overview')
  if (!response.ok) throw new Error('运营概览读取失败')
  return await response.json()
}

// ---- 签收正文复验 ----
export type ReverifyPack = {
  pack_id: string
  media_id: string
  version_id: string
  version_no: string
  signoff_digest: string
  receiver: string
  signed_at: string
  status: string
  verdict: string
  archived_digest: string
  reference_confirmed: boolean
  reference_state: string
  reference_id: string
  real_ref_count: number
  next_handler: string
  needs_handler: boolean
}

export type ReverifyCredential = {
  credential_id: string
  pack_id: string
  version_id: string
  version_no: string
  submitted_digest: string
  computed_digest: string
  archived_digest: string
  verdict: string
  code: string
  message: string
  reference_id: string
  reference_confirmed: boolean
  real_ref_count: number
  operator: string
  created_at: string
}

export type ReverifyResult = {
  ok: boolean
  verdict: string
  code: string
  message: string
  pack_id: string
  formal_reference: boolean
  became_formal_reference: boolean
  reference_state: string
  reference_id: string
  real_ref_count: number
  next_handler: string
  needs_handler: boolean
  notes: string[]
  credential: ReverifyCredential | null
  checks: {
    submitted_digest: string
    computed_digest: string
    archived_digest: string
  }
}

export type ReverifyStatus = {
  total: number
  confirmed: number
  unconfirmed: number
  credentials: number
}

export async function listReverifyPacks(): Promise<ReverifyPack[]> {
  const response = await request('/api/signoff_reverify/packs')
  if (!response.ok) throw new Error('历史签收包读取失败')
  return await response.json()
}

export async function listReverifyCredentials(): Promise<ReverifyCredential[]> {
  const response = await request('/api/signoff_reverify/credentials')
  if (!response.ok) throw new Error('归档凭据读取失败')
  return await response.json()
}

export async function loadReverifyStatus(): Promise<ReverifyStatus> {
  const response = await request('/api/signoff_reverify/status')
  if (!response.ok) throw new Error('复验总览读取失败')
  return await response.json()
}

export async function submitReverify(payload: {
  pack_id: string
  signoff_digest: string
  subtitles: string
  operator: string
}): Promise<ReverifyResult> {
  const response = await request('/api/signoff_reverify/verify', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  const body = await response.json()
  if (!response.ok) {
    throw new Error(body?.detail ?? '复验提交失败')
  }
  return body as ReverifyResult
}
