import { createI18n } from 'vue-i18n'
import en from './locales/en'
import zh from './locales/zh'

const saved = localStorage.getItem('lang') || 'zh'

export const i18n = createI18n({
  legacy: false,
  locale: saved,
  fallbackLocale: 'zh',
  messages: { en, zh },
})

export function switchLang() {
  const next = i18n.global.locale.value === 'zh' ? 'en' : 'zh'
  i18n.global.locale.value = next
  localStorage.setItem('lang', next)
}
