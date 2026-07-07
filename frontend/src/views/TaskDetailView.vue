<template>
  <div class="detail-page">
    <h2 class="page-title">{{ $t('task.title') }} {{ taskId }}</h2>

    <!-- initial loading / task not found -->
    <div v-if="!task" class="loading-box">
      <el-icon class="spinner" :size="48"><Loading /></el-icon>
      <p v-if="notFound">{{ $t('task.not_found') }}</p>
    </div>

    <!-- loading -->
    <div v-else-if="task.status === 'pending' || task.status === 'processing'" class="loading-box">
      <el-icon class="spinner" :size="48"><Loading /></el-icon>
      <p>{{ task.status === 'pending' ? $t('task.pending') : $t('task.processing') }}</p>
    </div>

    <!-- failed -->
    <div v-else-if="task.status === 'failed'" class="error-box">
      <el-result icon="error" :title="$t('task.failed')" :sub-title="task.error || 'Unknown error'" />
    </div>

    <!-- completed -->
    <template v-else-if="task.status === 'completed'">
      <div class="meta-bar">
        <span>{{ $t('task.cost') }}: <strong>{{ task.cost_ms }}ms</strong></span>
        <span>{{ $t('task.keypoints') }}: <strong>{{ task.keypoints }}</strong></span>
        <span>{{ $t('task.images') }}: <strong>{{ task.image_count }}</strong></span>
      </div>

      <div class="result-section">
        <h3>{{ $t('task.result') }} <span class="preview-hint">{{ $t('task.preview_hint') }}</span></h3>
        <div class="result-image-wrap">
          <el-image
            :src="resultSrc"
            :preview-src-list="[resultSrc]"
            :preview-teleported="true"
            fit="contain"
            class="result-el-image"
          >
            <template #placeholder>
              <img :src="thumbnailSrc" class="result-placeholder" alt="loading" />
            </template>
          </el-image>
        </div>
      </div>

      <div v-if="task.input_urls?.length" class="input-section">
        <h3>{{ $t('task.source_images') }}</h3>
        <div class="input-grid">
          <div v-for="url in task.input_urls" :key="url" class="input-item">
            <el-image :src="url" :preview-src-list="[url]" :preview-teleported="true" fit="cover" class="input-img" />
          </div>
        </div>
      </div>

      <div v-if="task.chart_urls?.length" class="analysis-section">
        <h3>{{ $t('task.charts') }}</h3>
        <div class="chart-grid">
          <div v-for="url in task.chart_urls" :key="url" class="chart-item">
            <img :src="url" :alt="url" />
          </div>
        </div>
      </div>

      <div v-if="tableData.length" class="table-section">
        <h3>{{ $t('task.tables') }}</h3>
        <div v-for="(tbl, idx) in tableData" :key="idx" class="table-card">
          <h4 class="table-title">{{ tbl.title }}</h4>
          <div class="table-wrap">
            <el-table :data="tbl.rows" border stripe size="small" max-height="400">
              <el-table-column
                v-for="(h, ci) in tbl.headers"
                :key="ci"
                :prop="String(ci)"
                :label="h"
                :min-width="120"
              />
            </el-table>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { Loading } from '@element-plus/icons-vue'
import { getTask } from '../api'

const route = useRoute()
const taskId = route.params.taskId
const task = ref(null)
const notFound = ref(false)
const tableData = ref([])
let timer = null

const thumbnailSrc = computed(() => `/api/thumbnail/${taskId}`)
const resultSrc = computed(() => `/api/result/${taskId}`)

async function fetchTables(urls) {
  if (!urls?.length) { tableData.value = []; return }
  const results = []
  for (const url of urls) {
    try {
      const res = await fetch(url)
      const json = await res.json()
      if (json && json.headers && json.rows) {
        results.push(json)
      }
    } catch { /* skip broken table */ }
  }
  tableData.value = results
}

async function poll() {
  try {
    const res = await getTask(taskId)
    if (res.code === 0) {
      task.value = res.data
      if (res.data.status === 'completed' || res.data.status === 'failed') {
        clearInterval(timer)
        if (res.data.table_urls) {
          fetchTables(res.data.table_urls)
        }
      }
    } else if (res.code === 404) {
      notFound.value = true
      clearInterval(timer)
    }
  } catch { /* retry next poll */ }
}

onMounted(() => { poll(); timer = setInterval(poll, 1000) })
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.detail-page { max-width: 900px; margin: 0 auto; }
.page-title { margin-bottom: 24px; font-size: 20px; word-break: break-all; }
.loading-box { text-align: center; padding: 80px 0; }
.spinner { animation: spin 1s linear infinite; color: #409EFF; }
.loading-box p { margin-top: 16px; font-size: 16px; color: #666; }
@keyframes spin { to { transform: rotate(360deg); } }
.error-box { padding: 60px 0; }
.meta-bar {
  display: flex;
  gap: 32px;
  margin-bottom: 32px;
  padding: 20px 24px;
  background: #fff;
  border-radius: 12px;
  font-size: 14px;
  color: #666;
  box-shadow: 0 1px 8px rgba(0, 0, 0, 0.04);
}
.meta-bar strong { color: #333; font-size: 18px; }
.result-section h3, .analysis-section h3, .table-section h3 { margin-bottom: 16px; font-size: 18px; font-weight: 600; }
.preview-hint { font-size: 12px; color: #999; font-weight: 400; }
.result-image-wrap {
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  cursor: pointer;
}
.result-el-image {
  width: 100%;
  display: block;
  max-height: 500px;
}
.result-el-image :deep(img) { max-height: 500px; object-fit: contain; }
.result-placeholder {
  width: 100%;
  display: block;
  max-height: 500px;
  object-fit: contain;
  filter: blur(8px);
}
.input-section { margin-top: 40px; }
.input-section h3 { margin-bottom: 16px; font-size: 18px; font-weight: 600; }
.input-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 12px; }
.input-item {
  background: #fff;
  border-radius: 10px;
  overflow: hidden;
  aspect-ratio: 4 / 3;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.05);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.input-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}
.input-img { width: 100%; height: 100%; }
.input-img :deep(img) { object-fit: cover; }

.analysis-section { margin-top: 40px; }
.chart-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.chart-item {
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 8px rgba(0, 0, 0, 0.04);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.chart-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}
.chart-item img { width: 100%; display: block; }

.table-section { margin-top: 40px; }
.table-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 1px 8px rgba(0, 0, 0, 0.04);
}
.table-title { margin: 0 0 16px; font-size: 15px; font-weight: 600; color: #333; }
.table-wrap { overflow-x: auto; }
</style>
