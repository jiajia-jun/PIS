import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

// 直接从后端 config.yaml 读取 host/port，与后端保持一致，只改一处即可
const __dirname = dirname(fileURLToPath(import.meta.url))
const yaml = readFileSync(resolve(__dirname, '../config.yaml'), 'utf-8')

const hostMatch = yaml.match(/^\s*host:\s*"([^"]*)"/m)
const portMatch = yaml.match(/^\s*port:\s*(\d+)/m)

const host = hostMatch?.[1] || 'localhost'
const port = portMatch?.[1] || '8081'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    proxy: {
      '/api': `http://${host}:${port}`,
    },
  },
})
