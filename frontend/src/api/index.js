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

export async function getHistory(page = 1, size = 10, status = '') {
  const params = new URLSearchParams({ page, size })
  if (status) params.set('status', status)
  const res = await fetch(`${BASE}/history?${params}`)
  return res.json()
}
