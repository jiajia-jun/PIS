<template>
  <div id="app">
    <div class="nav-bar">
      <div class="nav-inner">
        <el-menu
          mode="horizontal"
          :router="true"
          :default-active="$route.path"
          class="nav-menu"
        >
          <el-menu-item index="/">
            <el-icon><Upload /></el-icon>
            {{ $t('nav.upload') }}
          </el-menu-item>
          <el-menu-item index="/history">
            <el-icon><Clock /></el-icon>
            {{ $t('nav.history') }}
          </el-menu-item>
          <el-menu-item index="/about">
            <el-icon><UserFilled /></el-icon>
            {{ $t('nav.about') }}
          </el-menu-item>
        </el-menu>
        <el-button class="theme-btn" text @click="toggleDark">
          <el-icon :size="18"><component :is="isDark ? Sunny : Moon" /></el-icon>
        </el-button>
        <el-button class="lang-btn" text @click="toggleLang">
          {{ $i18n.locale === 'zh' ? 'EN' : '中' }}
        </el-button>
      </div>
    </div>
    <main class="app-main">
      <router-view v-slot="{ Component }">
        <transition name="fade-slide" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import { Upload, Clock, UserFilled, Moon, Sunny } from '@element-plus/icons-vue'
import { switchLang } from './i18n'
import { useDarkMode } from './composables/useDarkMode'

const { isDark, toggle: toggleDark } = useDarkMode()

function toggleLang() {
  switchLang()
  location.reload()
}
</script>

<style>
.nav-bar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--nav-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--nav-border);
  box-shadow: var(--nav-shadow);
}

.nav-inner {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  align-items: center;
}

.nav-menu {
  flex: 1;
  background: transparent !important;
  border-bottom: none !important;
}

.nav-menu .el-menu-item {
  border-bottom: 2px solid transparent !important;
}

.nav-menu .el-menu-item.is-active {
  border-bottom-color: #409EFF !important;
}

.theme-btn {
  margin-right: 4px;
  font-size: 14px;
}

.lang-btn {
  margin-right: 16px;
  font-size: 14px;
}

.app-main {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}
</style>
