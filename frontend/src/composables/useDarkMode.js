import { ref } from 'vue'

const STORAGE_KEY = 'pis_theme'

function loadPref() {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored) return stored === 'dark'
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

const isDark = ref(loadPref())

function apply() {
  document.documentElement.classList.toggle('dark', isDark.value)
}

// 首次导入时立即应用
apply()

export function useDarkMode() {
  function toggle() {
    isDark.value = !isDark.value
    localStorage.setItem(STORAGE_KEY, isDark.value ? 'dark' : 'light')
    apply()
  }

  return { isDark, toggle }
}
