<template>
  <div class="history-page">
    <h2 class="page-title">{{ $t('history.title') }}</h2>

    <!-- 状态筛选 -->
    <div class="history-toolbar">
      <el-radio-group v-model="statusFilter" size="small" @change="onFilterChange">
        <el-radio-button value="">{{ $t('history.filter_all') }}</el-radio-button>
        <el-radio-button value="completed">{{ $t('history.filter_completed') }}</el-radio-button>
        <el-radio-button value="failed">{{ $t('history.filter_failed') }}</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 空状态 -->
    <el-empty v-if="!loading && items.length === 0" :description="emptyDesc">
      <el-button v-if="statusFilter" type="primary" size="small" @click="statusFilter = ''; onFilterChange()">
        {{ $t('history.show_all') }}
      </el-button>
    </el-empty>

    <!-- 数据表格 -->
    <template v-else>
      <el-table :data="items" stripe style="width: 100%" @row-click="goDetail" row-class-name="clickable-row" v-loading="loading">
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
          @current-change="onPageChange"
          @size-change="onSizeChange"
        />
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { getHistory } from '../api'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()

const HISTORY_KEY = 'pis_history_page'

function loadPage() {
  const qp = Number(route.query.page)
  const qs = Number(route.query.size)
  if (qp >= 1) return { page: qp, size: qs >= 1 ? qs : 10 }
  try {
    const raw = sessionStorage.getItem(HISTORY_KEY)
    if (raw) {
      const v = JSON.parse(raw)
      if (v.p >= 1) return { page: v.p, size: v.s >= 1 ? v.s : 10 }
    }
  } catch { /* ignore */ }
  return { page: 1, size: 10 }
}

function savePage() {
  try { sessionStorage.setItem(HISTORY_KEY, JSON.stringify({ p: page.value, s: size.value })) } catch { /* ignore */ }
}

const initial = loadPage()
const items = ref([])
const total = ref(0)
const page = ref(initial.page)
const size = ref(initial.size)
const statusFilter = ref('')
const loading = ref(false)

const emptyDesc = computed(() => {
  return statusFilter.value
    ? t('history.empty_filtered')
    : t('history.empty_all')
})

function statusType(s) {
  const m = { completed: 'success', failed: 'danger', pending: 'info', processing: 'warning' }
  return m[s] || 'info'
}
function formatTime(ts) { return ts ? new Date(ts).toLocaleString() : '-' }
function indexMethod(idx) { return (page.value - 1) * size.value + idx + 1 }
function goDetail(row) { router.push(`/task/${row.task_id}`) }
function onSizeChange(v) { size.value = v; page.value = 1; update() }
function onPageChange() { update() }
function onFilterChange() { page.value = 1; update() }
function update() {
  savePage()
  router.replace({ query: { page: page.value, size: size.value } }).catch(() => {})
  fetchHistory()
}
async function fetchHistory() {
  loading.value = true
  try {
    const res = await getHistory(page.value, size.value, statusFilter.value)
    if (res.code === 0) { items.value = res.data.items || []; total.value = res.data.total || 0 }
  } catch { /* ignore */ }
  finally { loading.value = false }
}
onMounted(() => { update() })
onUnmounted(() => { savePage() })
</script>

<style scoped>
.page-title { margin-bottom: 20px; font-size: 22px; font-weight: 700; }
.history-toolbar {
  margin-bottom: 16px;
}
.task-id { font-family: monospace; font-size: 13px; }
:deep(.clickable-row) { cursor: pointer; transition: background 0.15s ease; }
:deep(.clickable-row:hover) { background: rgba(64, 158, 255, 0.04) !important; }
.pagination-wrap { margin-top: 24px; display: flex; justify-content: flex-end; }
</style>
