const BASE = '/api'

export async function uploadImages(files) {
  const form = new FormData()
  files.forEach((f) => form.append('images', f))
  const res = await fetch(`${BASE}/upload`, { method: 'POST', body: form })
  return res.json()
}

export async function getTask(taskId) {
  const res = await fetch(`${BASE}/task/${taskId}`)
  return res.json()
}

export async function getHistory(page = 1, size = 10) {
  const res = await fetch(`${BASE}/history?page=${page}&size=${size}`)
  return res.json()
}
