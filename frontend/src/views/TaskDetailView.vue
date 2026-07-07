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
        <h3>{{ $t('task.result') }}</h3>
        <div class="result-image-wrap">
          <img :src="thumbnailSrc" class="result-img result-thumb" alt="thumbnail" />
          <img :src="resultSrc" class="result-img result-original" :class="{ loaded: originalLoaded }" alt="panorama" @load="originalLoaded = true" />
        </div>
      </div>

      <div v-if="task.analysis_urls?.length" class="analysis-section">
        <h3>{{ $t('task.charts') }}</h3>
        <div class="chart-grid">
          <div v-for="url in task.analysis_urls" :key="url" class="chart-item">
            <img :src="url" :alt="url" />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { Loading } from '@element-plus/icons-vue'
import { getTask } from '../api'

const route = useRoute()
const taskId = route.params.taskId
const task = ref(null)
const notFound = ref(false)
const originalLoaded = ref(false)
let timer = null

const thumbnailSrc = computed(() => `/api/thumbnail/${taskId}`)
const resultSrc = computed(() => `/api/result/${taskId}`)

async function poll() {
  try {
    const res = await getTask(taskId)
    if (res.code === 0) {
      task.value = res.data
      if (res.data.status === 'completed' || res.data.status === 'failed') {
        clearInterval(timer)
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
.meta-bar { display: flex; gap: 32px; margin-bottom: 32px; padding: 16px 20px; background: #fff; border-radius: 8px; font-size: 14px; color: #666; }
.meta-bar strong { color: #333; }
.result-section h3, .analysis-section h3 { margin-bottom: 16px; font-size: 18px; }
.result-image-wrap { position: relative; background: #fff; border-radius: 8px; overflow: hidden; }
.result-img { width: 100%; display: block; }
.result-thumb { filter: blur(8px); }
.result-original { position: absolute; top: 0; left: 0; opacity: 0; transition: opacity 0.4s ease; }
.result-original.loaded { opacity: 1; }
.analysis-section { margin-top: 40px; }
.chart-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.chart-item { background: #fff; border-radius: 8px; overflow: hidden; }
.chart-item img { width: 100%; display: block; }
</style>
