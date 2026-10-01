<template>
  <section class="page" data-module="feeder">
    <header class="page-head">
      <div>
        <h2>支线驳船管理</h2>
        <p class="page-desc">维护驳船，围绕驳船编号、驳船名称、运营公司、载箱量做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记驳船</button>
        <button class="btn" type="button" @click="exportRows">导出支线驳船清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>驳船状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无支线驳船数据，可先登记驳船</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条支线驳船记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/feeder'
const columns = ["驳船编号", "驳船名称", "运营公司", "载箱量", "到港时间", "离港时间", "靠泊码头", "驳船状态"]
const actions = ["安排靠泊", "开始作业", "确认离港"]
const statuses = ["到港待靠", "靠泊中", "作业中", "已离港"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const statusFilter = ref('')
const filterFields = columns.slice(0, 3)

// 统计卡直接从列表数据算：接口没数据或载箱量读不到，页面一眼就能看出来
const stats = computed(() => {
  const waiting = rows.value.filter((row) => row['驳船状态'] === '到港待靠').length
  const inPort = rows.value.filter((row) => ['靠泊中', '作业中'].includes(String(row['驳船状态']))).length
  const departed = rows.value.filter((row) => row['驳船状态'] === '已离港').length
  const teuTotal = rows.value.reduce((sum, row) => sum + (Number(row['载箱量']) || 0), 0)
  return [
    { label: '待靠驳船', value: waiting },
    { label: '在港驳船', value: inPort },
    { label: '已离港驳船', value: departed },
    { label: '载箱量合计(TEU)', value: teuTotal },
  ]
})

function resetFilters() {
  filters.value = {}
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '驳船登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('支线驳船动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '支线驳船操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams(filters.value as Record<string, string>)
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  const query = params.toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('驳船列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '支线驳船列表读取失败'
  }
}

onMounted(reload)
</script>
