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
        </el-menu>
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
import { Upload, Clock } from '@element-plus/icons-vue'
import { switchLang } from './i18n'

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
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  box-shadow: 0 1px 8px rgba(0, 0, 0, 0.04);
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
