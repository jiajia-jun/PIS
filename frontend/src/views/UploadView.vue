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
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { uploadImages } from '../api'

const { t } = useI18n()
const router = useRouter()
const MAX_SIZE = 200 * 1024 * 1024

const fileList = ref([])
const uploading = ref(false)

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
  max-width: 560px;
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
