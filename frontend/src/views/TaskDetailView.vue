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
        <div
          class="result-image-wrap"
          ref="zoomWrap"
          @mousemove="onZoomMove"
          @mouseenter="onZoomEnter"
          @mouseleave="onZoomLeave"
        >
          <img :src="resultSrc" class="result-el-image" alt="panorama" />
          <div
            v-show="zooming"
            class="zoom-lens"
            :style="lensStyle"
          ></div>
        </div>
      </div>

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
          <div v-for="url in task.input_urls" :key="url" class="input-item">
            <el-image :src="url" :preview-src-list="[url]" :preview-teleported="true" fit="cover" class="input-img" />
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
import { Loading } from '@element-plus/icons-vue'
import { getTask } from '../api'

const route = useRoute()
const taskId = route.params.taskId
const task = ref(null)
const notFound = ref(false)
const tableData = ref([])
let timer = null

// ---- 鼠标位置缩放（放大镜） ----
const zoomWrap = ref(null)
const zooming = ref(false)
const lensStyle = ref({})

const ZOOM = 2.5
const LENS = 180  // 放大镜尺寸 px

function onZoomEnter() { zooming.value = true }
function onZoomLeave() { zooming.value = false }
function onZoomMove(e) {
  const wrap = zoomWrap.value
  if (!wrap) return
  const rect = wrap.getBoundingClientRect()
  const x = e.clientX - rect.left   // 鼠标在容器内 X
  const y = e.clientY - rect.top    // 鼠标在容器内 Y

  // 放大镜背景图为结果大图，background-size 按容器尺寸 × ZOOM 放大
  // background-position 把鼠标指向的点对齐到放大镜中心
  const bgX = -(x * ZOOM) + LENS / 2
  const bgY = -(y * ZOOM) + LENS / 2

  lensStyle.value = {
    left: `${x - LENS / 2}px`,
    top: `${y - LENS / 2}px`,
    width: `${LENS}px`,
    height: `${LENS}px`,
    backgroundImage: `url(${resultSrc.value})`,
    backgroundSize: `${rect.width * ZOOM}px ${rect.height * ZOOM}px`,
    backgroundPosition: `${bgX}px ${bgY}px`,
    backgroundRepeat: 'no-repeat',
  }
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
  const isPct = ['内点率', '重叠区SSIM', '有效画布占比', '清晰度保持率', '综合得分'].includes(label)
  if (isPct) return (v * 100).toFixed(1) + '%'
  if (label === '重投影RMSE') return v.toFixed(2) + ' px'
  return typeof val === 'number' ? val.toFixed(4) : String(val)
}

const evalRows = computed(() => {
  if (!evalData.value) return []
  const fields = ['内点率', '重投影RMSE', '重叠区SSIM', '有效画布占比', '清晰度保持率', '综合得分']
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
        if (res.data.status === 'completed') {
          fetchEvalData()
          fetchFullMetrics()
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
.result-section h3, .analysis-section h3, .table-section h3, .input-section h3 {
  margin-bottom: 16px; font-size: 18px; font-weight: 600;
}
.preview-hint { font-size: 12px; color: #999; font-weight: 400; }
.result-image-wrap {
  position: relative;
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  cursor: none;
  max-height: 500px;
}
.result-el-image {
  width: 100%;
  display: block;
  max-height: 500px;
  object-fit: contain;
  user-select: none;
  -webkit-user-drag: none;
}
.zoom-lens {
  position: absolute;
  border-radius: 50%;
  border: 2px solid rgba(255,255,255,.8);
  box-shadow: 0 0 0 2px rgba(0,0,0,.3), 0 4px 16px rgba(0,0,0,.4);
  pointer-events: none;
  z-index: 10;
}

/* ===== 评估摘要区 ===== */
.eval-summary {
  margin-top: 40px;
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 1px 8px rgba(0, 0, 0, 0.04);
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
  background: #f5f7fa;
  color: #666;
  font-weight: 600;
  border-bottom: 2px solid #e4e7ed;
}
.eval-table td {
  padding: 10px 12px;
  border-bottom: 1px solid #ebeef5;
}
.eval-label { color: #333; font-weight: 500; }
.eval-value { color: #333; font-weight: 600; font-variant-numeric: tabular-nums; }
.eval-radar {
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 240px;
  background: #fafbfc;
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
  color: #ccc;
  font-size: 14px;
}

/* ===== 详细数据折叠面板 ===== */
.detail-section {
  margin-top: 24px;
}
.collapse-title {
  font-size: 15px;
  font-weight: 600;
  color: #555;
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
  color: #ccc;
}

/* ===== 原始图片 ===== */
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

/* ===== 分析图表 ===== */
.analysis-section { margin-top: 40px; }
.chart-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.chart-item {
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 8px rgba(0, 0, 0, 0.04);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  cursor: pointer;
}
.chart-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}
.chart-el-img { width: 100%; display: block; }
.chart-el-img :deep(img) { object-fit: contain; }

/* ===== 分析表格 ===== */
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
