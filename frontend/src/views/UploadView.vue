<template>
  <div class="upload-page">
    <div class="upload-card">
      <h2 class="upload-title">{{ $t('upload.title') }}</h2>
      <p class="upload-desc">{{ $t('upload.desc') }}</p>

      <el-upload
        ref="uploadRef"
        drag
        multiple
        :auto-upload="false"
        :limit="20"
        accept="image/*"
        v-model:file-list="fileList"
        :show-file-list="false"
        @exceed="onExceed"
      >
        <div class="upload-area">
          <el-icon class="upload-icon"><UploadFilled /></el-icon>
          <div class="upload-text">
            <em>{{ $t('upload.click') }}</em> {{ $t('upload.or') }}
          </div>
          <div class="upload-hint">{{ $t('upload.hint') }}</div>
        </div>
      </el-upload>

      <!-- 文件预览网格 -->
      <div v-if="fileList.length > 0" class="file-preview-section">
        <div class="file-preview-header">
          <span>{{ $t('upload.selected_count', { n: fileList.length }) }}</span>
          <el-button type="danger" text size="small" @click="clearAll">{{ $t('upload.clear_all') }}</el-button>
        </div>
        <div class="file-preview-grid">
          <div v-for="(file, idx) in fileList" :key="file.uid" class="file-preview-item">
            <div class="file-preview-img-wrap">
              <img :src="getPreviewUrl(file)" class="file-preview-img" />
              <div class="file-preview-remove" @click="removeFile(idx)">
                <el-icon :size="14"><Close /></el-icon>
              </div>
            </div>
            <div class="file-preview-name" :title="file.name">{{ file.name }}</div>
            <div class="file-preview-size">{{ formatSize(file.size || file.raw?.size) }}</div>
          </div>
        </div>
      </div>

      <div class="upload-actions">
        <el-button
          type="primary"
          size="large"
          :disabled="fileList.length === 0"
          :loading="uploading"
          @click="doUpload"
        >
          {{ uploading ? $t('upload.uploading') : $t('upload.btn_stitch', { n: fileList.length }) }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { UploadFilled, Close } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { uploadImages } from '../api'

const { t } = useI18n()
const router = useRouter()
const MAX_SIZE = 200 * 1024 * 1024

const fileList = ref([])
const uploading = ref(false)
const uploadRef = ref(null)

function formatSize(bytes) {
  if (!bytes || bytes === 0) return '-'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function getPreviewUrl(file) {
  // el-upload 对未上传的文件不会自动生成 url，手动创建 blob URL
  if (file.url) return file.url
  if (file.raw instanceof File) return URL.createObjectURL(file.raw)
  return ''
}

function removeFile(idx) {
  const file = fileList.value[idx]
  // 用 el-upload 内部方法移除，保持组件状态同步
  if (uploadRef.value) {
    uploadRef.value.handleRemove(file)
  } else {
    fileList.value.splice(idx, 1)
  }
}

function clearAll() {
  if (uploadRef.value) {
    uploadRef.value.clearFiles()
  } else {
    fileList.value = []
  }
}

function onExceed() {
  ElMessage.warning(t('upload.limit_exceed'))
}

async function doUpload() {
  if (fileList.value.length === 0) return

  const rawFiles = fileList.value.map((f) => f.raw)
  const oversized = rawFiles.find((f) => f.size > MAX_SIZE)
  if (oversized) {
    ElMessage.warning(t('upload.size_exceed', { name: oversized.name }))
    return
  }

  uploading.value = true
  try {
    const res = await uploadImages(rawFiles)
    if (res.code === 0 && res.data?.task_id) {
      router.push(`/task/${res.data.task_id}`)
    } else {
      ElMessage.error(res.message || t('upload.failed'))
    }
  } catch {
    ElMessage.error(t('upload.network_error'))
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.upload-page {
  display: flex;
  justify-content: center;
  padding-top: 48px;
}
.upload-card {
  width: 100%;
  max-width: 620px;
  background: #fff;
  border-radius: 16px;
  padding: 40px;
  box-shadow: 0 2px 16px rgba(0, 0, 0, 0.06), 0 0 0 1px rgba(0, 0, 0, 0.04);
}
.upload-title {
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 8px;
  text-align: center;
}
.upload-desc {
  color: #666;
  margin-bottom: 32px;
  text-align: center;
}
.upload-area {
  padding: 40px 20px;
}
.upload-icon {
  font-size: 48px;
  color: #409EFF;
  margin-bottom: 12px;
}
.upload-text {
  font-size: 16px;
  color: #333;
  margin-bottom: 6px;
}
.upload-text em {
  color: #409EFF;
  font-style: normal;
}
.upload-hint {
  font-size: 12px;
  color: #bbb;
}

/* ---- 文件预览 ---- */
.file-preview-section {
  margin-top: 20px;
  border-top: 1px solid #ebeef5;
  padding-top: 16px;
}
.file-preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 13px;
  color: #909399;
}
.file-preview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 10px;
}
.file-preview-item {
  background: #fafbfc;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #ebeef5;
  transition: border-color 0.2s;
}
.file-preview-item:hover {
  border-color: #c6d0db;
}
.file-preview-img-wrap {
  position: relative;
  aspect-ratio: 4 / 3;
  background: #f0f1f3;
  overflow: hidden;
}
.file-preview-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.file-preview-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s;
}
.file-preview-img-wrap:hover .file-preview-remove {
  opacity: 1;
}
.file-preview-name {
  font-size: 11px;
  color: #333;
  padding: 4px 6px 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.file-preview-size {
  font-size: 10px;
  color: #bbb;
  padding: 0 6px 6px;
}

.upload-actions {
  margin-top: 24px;
  text-align: center;
}
.upload-actions .el-button {
  min-width: 200px;
  border-radius: 8px;
  font-weight: 600;
  transition: all 0.2s ease;
}
.upload-actions .el-button:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.35);
}
</style>
