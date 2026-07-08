import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import en from 'element-plus/dist/locale/en.mjs'
import App from './App.vue'
import router from './router'
import { i18n } from './i18n'

const app = createApp(App)

// Element Plus 语言跟随 i18n 切换
const elLocales = { zh: zhCn, en }
const elLocale = elLocales[localStorage.getItem('lang') || 'zh'] || zhCn
app.use(ElementPlus, { locale: elLocale })
app.use(router)
app.use(i18n)
app.mount('#app')
