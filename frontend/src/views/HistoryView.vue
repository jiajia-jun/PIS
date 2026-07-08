<template>
  <div class="history-page">
    <h2 class="page-title">{{ $t('history.title') }}</h2>

    <el-table :data="items" stripe style="width: 100%" @row-click="goDetail" row-class-name="clickable-row">
      <el-table-column type="index" :label="$t('history.index')" width="60" :index="indexMethod" />

      <el-table-column :label="$t('history.task_id')" min-width="200">
        <template #default="{ row }">
          <span class="task-id">{{ row.task_id.slice(0, 8) }}...</span>
        </template>
      </el-table-column>

      <el-table-column :label="$t('history.status')" width="120">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column :label="$t('history.images')" width="80" prop="image_count" />

      <el-table-column :label="$t('history.keypoints')" width="100">
        <template #default="{ row }">{{ row.keypoints || '-' }}</template>
      </el-table-column>

      <el-table-column :label="$t('history.cost')" width="100">
        <template #default="{ row }">{{ row.cost_ms ? row.cost_ms + 'ms' : '-' }}</template>
      </el-table-column>

      <el-table-column :label="$t('history.created')" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        :page-size="size"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @current-change="fetchHistory"
        @size-change="onSizeChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { getHistory } from '../api'

const router = useRouter()
const route = useRoute()
const items = ref([])
const total = ref(0)
const page = ref(Number(route.query.page) || 1)
const size = ref(Number(route.query.size) || 10)

function statusType(s) {
  const m = { completed: 'success', failed: 'danger', pending: 'info', processing: 'warning' }
  return m[s] || 'info'
}
function formatTime(ts) { return ts ? new Date(ts).toLocaleString() : '-' }
function indexMethod(idx) { return (page.value - 1) * size.value + idx + 1 }
function goDetail(row) { router.push(`/task/${row.task_id}`) }
function onSizeChange(v) { size.value = v; page.value = 1; syncQuery(); fetchHistory() }
function syncQuery() {
  router.replace({ query: { page: page.value, size: size.value } })
}
async function fetchHistory() {
  try {
    const res = await getHistory(page.value, size.value)
    if (res.code === 0) { items.value = res.data.items || []; total.value = res.data.total || 0 }
  } catch { /* ignore */ }
}
onMounted(fetchHistory)
watch(page, syncQuery)
</script>

<style scoped>
.page-title { margin-bottom: 24px; font-size: 22px; font-weight: 700; }
.task-id { font-family: monospace; font-size: 13px; }
:deep(.clickable-row) { cursor: pointer; transition: background 0.15s ease; }
:deep(.clickable-row:hover) { background: rgba(64, 158, 255, 0.04) !important; }
.pagination-wrap { margin-top: 24px; display: flex; justify-content: flex-end; }
</style>
