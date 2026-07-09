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
      <p class="elapsed-text">{{ $t('task.elapsed', { n: elapsed }) }}</p>
      <p class="mode-text">{{ $t('task.mode_label') }}: {{ task.mode === 'super' ? $t('task.mode_super_label') : $t('task.mode_normal_label') }}</p>
      <p class="leave-hint">{{ $t('task.can_leave_hint') }}</p>
    </div>

    <!-- failed -->
    <template v-else-if="task.status === 'failed'">
      <div class="error-box">
        <el-result icon="error" :title="$t('task.failed')" :sub-title="task.error || 'Unknown error'" />
      </div>

      <!-- 失败时也展示原始图片 -->
      <div v-if="task.input_urls?.length" class="input-section">
        <h3>{{ $t('task.source_images') }}</h3>
        <div class="input-grid">
          <div v-for="(url, idx) in task.input_urls" :key="url" class="input-item">
            <el-image :src="url" :preview-src-list="[url]" :preview-teleported="true" fit="cover" class="input-img">
              <template #placeholder>
                <img :src="task.input_thumb_urls?.[idx]" class="input-thumb-placeholder" />
              </template>
            </el-image>
          </div>
        </div>
      </div>
    </template>

    <!-- completed -->
    <template v-else-if="task.status === 'completed'">
      <div class="meta-bar">
        <span>{{ $t('task.cost') }}: <strong>{{ task.cost_ms }}ms</strong></span>
        <span>{{ $t('task.keypoints') }}: <strong>{{ task.keypoints }}</strong></span>
        <span>{{ $t('task.images') }}: <strong>{{ task.image_count }}</strong></span>
        <span>{{ $t('task.mode_label') }}: <strong>{{ task.mode === 'super' ? $t('task.mode_super_label') : $t('task.mode_normal_label') }}</strong></span>
      </div>

      <div class="result-section">
        <h3>{{ $t('task.result') }} <span class="preview-hint">{{ $t('task.preview_hint') }}</span></h3>
        <div class="result-image-wrap" @click="openViewer">
          <el-image
            :src="resultSrc"
            :preview-src-list="[]"
            :preview-teleported="false"
            fit="contain"
            class="result-el-image"
          >
            <template #placeholder>
              <img :src="thumbnailSrc" class="result-placeholder" alt="loading" />
            </template>
          </el-image>
          <div class="result-overlay">
            <el-icon :size="48"><ZoomIn /></el-icon>
          </div>
        </div>
      </div>

      <!-- ===== 全屏大图查看器 ===== -->
      <Teleport to="body">
        <div
          v-if="viewerOpen"
          class="img-viewer-mask"
          @mousedown="onViewerBgDown"
          @wheel.prevent="onViewerWheel"
        >
          <div class="img-viewer-toolbar">
            <span class="viewer-zoom-label">{{ Math.round(viewerScale * 100) }}%</span>
            <el-button circle size="small" @click="viewerScale = Math.min(5, viewerScale + 0.5)"><el-icon><ZoomIn /></el-icon></el-button>
            <el-button circle size="small" @click="viewerScale = Math.max(0.2, viewerScale - 0.5)"><el-icon><ZoomOut /></el-icon></el-button>
            <el-button circle size="small" @click="viewerScale = 1; viewerX = 0; viewerY = 0">{{ $t('task.reset') }}</el-button>
            <el-button circle size="small" type="danger" @click="closeViewer"><el-icon><Close /></el-icon></el-button>
          </div>
          <img
            ref="viewerImg"
            :src="resultSrc"
            class="img-viewer-main"
            :style="viewerImgStyle"
            @mousedown.prevent="onViewerDragStart"
            @load="onViewerImgLoad"
            draggable="false"
          />
        </div>
      </Teleport>

      <!-- ===== 拼接质量评估摘要区 ===== -->
      <div v-if="hasEvalData" class="eval-summary">
        <h3>{{ $t('eval.title') }}</h3>
        <div class="eval-content">
          <!-- 左：6 指标表格 -->
          <div class="eval-table-wrap">
            <table class="eval-table">
              <thead>
                <tr>
                  <th>{{ $t('eval.metric') }}</th>
                  <th>{{ $t('eval.value') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in evalRows" :key="row.label">
                  <td class="eval-label">{{ row.label }}</td>
                  <td class="eval-value">{{ row.display }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <!-- 右：雷达图 -->
          <div class="eval-radar">
            <el-image
              v-if="radarSrc"
              :src="radarSrc"
              :preview-src-list="[radarSrc]"
              :preview-teleported="true"
              fit="contain"
              class="radar-img"
            >
              <template #placeholder>
                <div class="radar-placeholder">
                  <el-icon class="spinner" :size="32"><Loading /></el-icon>
                </div>
              </template>
            </el-image>
            <div v-else class="radar-empty">
              <span>{{ $t('eval.no_radar') }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ===== 详细数据折叠面板 ===== -->
      <div v-if="hasDetailData" class="detail-section">
        <el-collapse v-model="activeCollapse">
          <el-collapse-item name="detail">
            <template #title>
              <span class="collapse-title">{{ $t('eval.detail_title') }}</span>
            </template>

            <el-tabs v-model="activeDetailTab" type="border-card" class="detail-tabs">
              <el-tab-pane
                v-for="group in detailGroups"
                :key="group.name"
                :label="group.name"
                :name="group.name"
              >
                <el-descriptions :column="2" border size="small" class="detail-desc">
                  <el-descriptions-item
                    v-for="item in group.items"
                    :key="item.label"
                    :label="item.label"
                    :span="1"
                  >
                    <span v-if="item.value !== null && item.value !== undefined" class="detail-val">
                      {{ item.value }}
                    </span>
                    <span v-else class="detail-na">N/A</span>
                  </el-descriptions-item>
                </el-descriptions>
              </el-tab-pane>
            </el-tabs>
          </el-collapse-item>
        </el-collapse>
      </div>

      <!-- ===== 原始图片 ===== -->
      <div v-if="task.input_urls?.length" class="input-section">
        <h3>{{ $t('task.source_images') }}</h3>
        <div class="input-grid">
          <div v-for="(url, idx) in task.input_urls" :key="url" class="input-item">
            <el-image :src="url" :preview-src-list="[url]" :preview-teleported="true" fit="cover" class="input-img">
              <template #placeholder>
                <img :src="task.input_thumb_urls?.[idx]" class="input-thumb-placeholder" />
              </template>
            </el-image>
          </div>
        </div>
      </div>

      <!-- ===== 分析图表（原有 grid，去重雷达图后展示其余） ===== -->
      <div v-if="otherChartUrls.length" class="analysis-section">
        <h3>{{ $t('task.charts') }}</h3>
        <div class="chart-grid">
          <div v-for="url in otherChartUrls" :key="url" class="chart-item">
            <el-image
              :src="url"
              :preview-src-list="[url]"
              :preview-teleported="true"
              fit="contain"
              class="chart-el-img"
            />
          </div>
        </div>
      </div>

      <!-- ===== 分析数据表格（原有） ===== -->
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
import { Loading, ZoomIn, ZoomOut, Close } from '@element-plus/icons-vue'
import { getTask } from '../api'

const route = useRoute()
const taskId = route.params.taskId
const task = ref(null)
const notFound = ref(false)
const tableData = ref([])
const now = ref(Date.now())
let timer = null
let elapsedTimer = null

const elapsed = computed(() => {
  if (!task.value?.created_at) return 0
  const created = new Date(task.value.created_at).getTime()
  return Math.max(0, Math.floor((now.value - created) / 1000))
})

// ---- 全屏大图查看器 ----
const viewerOpen = ref(false)
const viewerImg = ref(null)
const viewerScale = ref(1)
const viewerX = ref(0)
const viewerY = ref(0)
const dragging = ref(false)
const dragStart = ref({ x: 0, y: 0 })
const imgStart = ref({ x: 0, y: 0 })
const imgNatural = ref({ w: 0, h: 0 })

const viewerImgStyle = computed(() => ({
  transform: `translate(${viewerX.value}px, ${viewerY.value}px) scale(${viewerScale.value})`,
  cursor: dragging.value ? 'grabbing' : 'grab',
  transition: dragging.value ? 'none' : 'transform 0.15s ease-out',
}))

function openViewer() {
  viewerOpen.value = true; viewerScale.value = 1; viewerX.value = 0; viewerY.value = 0
  window.addEventListener('keydown', onViewerKeydown)
}
function closeViewer() {
  viewerOpen.value = false
  window.removeEventListener('keydown', onViewerKeydown)
}
function onViewerKeydown(e) {
  if (e.key === 'Escape') closeViewer()
}
function onViewerImgLoad() {
  if (viewerImg.value) {
    imgNatural.value = { w: viewerImg.value.naturalWidth, h: viewerImg.value.naturalHeight }
  }
}

// 滚轮缩放，以鼠标位置为中心
function onViewerWheel(e) {
  const img = viewerImg.value
  if (!img) return
  const rect = img.parentElement.getBoundingClientRect()
  // 视口中心（图片默认 flexbox 居中于 mask）
  const cx = rect.width / 2
  const cy = rect.height / 2
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top

  const oldScale = viewerScale.value
  let newScale = oldScale * (e.deltaY < 0 ? 1.15 : 0.85)
  newScale = Math.max(0.2, Math.min(5, newScale))

  // viewerX/Y 是从视口中心的平移量，保持鼠标指向的图片点不动
  const ratio = newScale / oldScale
  viewerX.value = viewerX.value * ratio + (1 - ratio) * (mx - cx)
  viewerY.value = viewerY.value * ratio + (1 - ratio) * (my - cy)
  viewerScale.value = newScale
}

// 拖拽
function onViewerDragStart(e) {
  if (viewerScale.value <= 1 && e.target === viewerImg.value) {
    // 未放大时仍允许拖拽观察边缘
  }
  dragging.value = true
  dragStart.value = { x: e.clientX, y: e.clientY }
  imgStart.value = { x: viewerX.value, y: viewerY.value }
  window.addEventListener('mousemove', onViewerDragMove)
  window.addEventListener('mouseup', onViewerDragEnd)
}
function onViewerDragMove(e) {
  if (!dragging.value) return
  viewerX.value = imgStart.value.x + (e.clientX - dragStart.value.x)
  viewerY.value = imgStart.value.y + (e.clientY - dragStart.value.y)
}
function onViewerDragEnd() {
  dragging.value = false
  window.removeEventListener('mousemove', onViewerDragMove)
  window.removeEventListener('mouseup', onViewerDragEnd)
}

// 点击背景关闭（点图片本身不关闭）
function onViewerBgDown(e) {
  if (e.target === e.currentTarget) closeViewer()
}

// ---- 评估数据 ----
const evalData = ref(null)       // eval_result.json
const fullMetrics = ref(null)    // full_metrics.json
const activeCollapse = ref([])
const activeDetailTab = ref('匹配质量')

const thumbnailSrc = computed(() => `/api/thumbnail/${taskId}`)
const resultSrc = computed(() => `/api/result/${taskId}`)

const hasEvalData = computed(() => evalData.value && evalData.value['状态'] === '成功')
const hasDetailData = computed(() => fullMetrics.value && fullMetrics.value['分组'])

// 评级阈值与逻辑
function formatVal(label, val) {
  if (val == null || val === '-' || val === undefined) return '-'
  const v = typeof val === 'string' ? parseFloat(val) : val
  if (isNaN(v)) return String(val)
  const isPct = ['内点率', '全景SSIM', '有效画布占比', '清晰度保持率', '综合得分'].includes(label)
  if (isPct) return (v * 100).toFixed(1) + '%'
  if (label === '重投影RMSE') return v.toFixed(2) + ' px'
  return typeof val === 'number' ? val.toFixed(4) : String(val)
}

const evalRows = computed(() => {
  if (!evalData.value) return []
  const fields = ['内点率', '重投影RMSE', '全景SSIM', '有效画布占比', '清晰度保持率', '综合得分']
  return fields.map(label => {
    const val = evalData.value[label]
    return { label, value: val, display: formatVal(label, val) }
  })
})

const detailGroups = computed(() => {
  if (!fullMetrics.value || !fullMetrics.value['分组']) return []
  return Object.entries(fullMetrics.value['分组']).map(([name, items]) => ({
    name,
    items: Object.entries(items).map(([label, value]) => ({
      label,
      value: value !== null && value !== undefined
        ? (typeof value === 'number' ? value.toFixed(6) : String(value))
        : null
    }))
  }))
})

// 雷达图 URL
const radarSrc = computed(() => {
  if (!task.value?.chart_urls?.length) return null
  return task.value.chart_urls.find(u => u.includes('quality_radar')) || null
})

// 其余图表（排除雷达图、gauge 大图，避免重复展示）
const otherChartUrls = computed(() => {
  if (!task.value?.chart_urls?.length) return []
  return task.value.chart_urls.filter(u =>
    !u.includes('quality_radar') && !u.includes('gauge_')
  )
})

// ---- 数据加载 ----
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

async function fetchEvalData() {
  try {
    const res = await fetch(`/api/analysis/${taskId}/eval_result.json`)
    if (res.ok) {
      evalData.value = await res.json()
    }
  } catch { /* skip */ }
}

async function fetchFullMetrics() {
  try {
    const res = await fetch(`/api/analysis/${taskId}/full_metrics.json`)
    if (res.ok) {
      fullMetrics.value = await res.json()
      // 自动展开折叠面板 + 默认选中第一个有数据的分组
      if (fullMetrics.value?.分组) {
        activeCollapse.value = ['detail']
        const names = Object.keys(fullMetrics.value.分组)
        if (names.length) activeDetailTab.value = names[0]
      }
    }
  } catch { /* skip */ }
}

function startElapsedTimer() {
  if (elapsedTimer) return
  elapsedTimer = setInterval(() => { now.value = Date.now() }, 1000)
}

function stopElapsedTimer() {
  if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null }
}

async function poll() {
  try {
    const res = await getTask(taskId)
    if (res.code === 0) {
      task.value = res.data
      if (res.data.status === 'completed' || res.data.status === 'failed') {
        clearInterval(timer)
        stopElapsedTimer()
        if (res.data.table_urls) {
          fetchTables(res.data.table_urls)
        }
        if (res.data.status === 'completed') {
          fetchEvalData()
          fetchFullMetrics()
        }
      }
    } else if (res.code === 404) {
      notFound.value = true
      clearInterval(timer)
      stopElapsedTimer()
    }
  } catch { /* retry next poll */ }
}

onMounted(() => { poll(); startElapsedTimer(); timer = setInterval(poll, 1000) })
onUnmounted(() => { clearInterval(timer); stopElapsedTimer() })
</script>

<style scoped>
.detail-page { max-width: 900px; margin: 0 auto; }
.page-title { margin-bottom: 24px; font-size: 20px; word-break: break-all; }
.loading-box { text-align: center; padding: 80px 0; }
.spinner { animation: spin 1s linear infinite; color: var(--accent); }
.loading-box p { margin-top: 16px; font-size: 16px; color: var(--text-tertiary); }
.elapsed-text { font-size: 13px !important; color: var(--text-light) !important; margin-top: 6px !important; }
.mode-text { font-size: 14px; color: var(--accent); font-weight: 600; margin-top: 6px; }
.leave-hint { font-size: 13px; color: var(--text-light); margin-top: 6px; }
@keyframes spin { to { transform: rotate(360deg); } }
.error-box { padding: 60px 0; }
.meta-bar {
  display: flex;
  gap: 32px;
  margin-bottom: 32px;
  padding: 20px 24px;
  background: var(--bg-card);
  border-radius: 12px;
  font-size: 14px;
  color: var(--text-tertiary);
  box-shadow: var(--shadow-sm);
}
.meta-bar strong { color: var(--text-primary); font-size: 18px; }
.result-section h3, .analysis-section h3, .table-section h3, .input-section h3 {
  margin-bottom: 16px; font-size: 18px; font-weight: 600;
}
.preview-hint { font-size: 12px; color: var(--text-hint); font-weight: 400; }
.result-image-wrap {
  position: relative;
  background: var(--bg-card);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: var(--shadow-result);
  cursor: pointer;
  max-height: 500px;
}
.result-image-wrap:hover .result-overlay { opacity: 1; }
.result-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,.35);
  opacity: 0;
  transition: opacity .25s;
  pointer-events: none;
  color: #fff;
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

/* ===== 全屏大图查看器 ===== */
.img-viewer-mask {
  position: fixed;
  inset: 0;
  z-index: 3000;
  background: rgba(0,0,0,.92);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.img-viewer-toolbar {
  position: absolute;
  top: 16px;
  right: 20px;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 8px;
}
.viewer-zoom-label {
  color: #ccc;
  font-size: 13px;
  min-width: 48px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.img-viewer-main {
  max-width: 90vw;
  max-height: 90vh;
  user-select: none;
  -webkit-user-drag: none;
}

/* ===== 评估摘要区 ===== */
.eval-summary {
  margin-top: 40px;
  background: var(--bg-card);
  border-radius: 12px;
  padding: 24px;
  box-shadow: var(--shadow-sm);
}
.eval-summary h3 {
  margin: 0 0 20px;
  font-size: 18px;
  font-weight: 600;
}
.eval-content {
  display: flex;
  gap: 32px;
  align-items: flex-start;
}
.eval-table-wrap {
  flex: 0 0 auto;
  min-width: 340px;
}
.eval-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.eval-table th {
  text-align: left;
  padding: 8px 12px;
  background: var(--bg-tag);
  color: var(--text-tertiary);
  font-weight: 600;
  border-bottom: 2px solid var(--border-table);
}
.eval-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
}
.eval-label { color: var(--text-primary); font-weight: 500; }
.eval-value { color: var(--text-primary); font-weight: 600; font-variant-numeric: tabular-nums; }
.eval-radar {
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 240px;
  background: var(--bg-card-alt);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: box-shadow 0.2s;
}
.eval-radar:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
.radar-img { width: 100%; max-height: 300px; }
.radar-img :deep(img) { max-height: 300px; object-fit: contain; }
.radar-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 240px;
}
.radar-empty {
  color: var(--text-light);
  font-size: 14px;
}

/* ===== 详细数据折叠面板 ===== */
.detail-section {
  margin-top: 24px;
}
.collapse-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary);
}
.detail-tabs {
  margin-top: 8px;
  box-shadow: none;
}
.detail-desc {
  margin-top: 8px;
}
.detail-desc :deep(.el-descriptions__label) {
  font-weight: 500;
  width: 180px;
}
.detail-val {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.detail-na {
  color: var(--text-light);
}

/* ===== 原始图片 ===== */
.input-section { margin-top: 40px; }
.input-section h3 { margin-bottom: 16px; font-size: 18px; font-weight: 600; }
.input-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 12px; }
.input-item {
  background: var(--bg-card);
  border-radius: 10px;
  overflow: hidden;
  aspect-ratio: 4 / 3;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.05);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.input-item:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-hover);
}
.input-img { width: 100%; height: 100%; }
.input-img :deep(img) { object-fit: cover; }
.input-thumb-placeholder { width: 100%; height: 100%; object-fit: cover; filter: blur(4px); }

/* ===== 分析图表 ===== */
.analysis-section { margin-top: 40px; }
.chart-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.chart-item {
  background: var(--bg-card);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  cursor: pointer;
}
.chart-item:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-chart-hover);
}
.chart-el-img { width: 100%; display: block; }
.chart-el-img :deep(img) { object-fit: contain; }

/* ===== 分析表格 ===== */
.table-section { margin-top: 40px; }
.table-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: var(--shadow-sm);
}
.table-title { margin: 0 0 16px; font-size: 15px; font-weight: 600; color: var(--text-primary); }
.table-wrap { overflow-x: auto; }
</style>
