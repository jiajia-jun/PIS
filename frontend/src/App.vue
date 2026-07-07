<template>
  <div id="app">
    <div class="nav-bar">
      <el-menu
        mode="horizontal"
        :router="true"
        :default-active="$route.path"
      >
        <el-menu-item index="/">{{ $t('nav.upload') }}</el-menu-item>
        <el-menu-item index="/history">{{ $t('nav.history') }}</el-menu-item>
      </el-menu>
      <el-button class="lang-btn" text @click="toggleLang">
        {{ $i18n.locale === 'zh' ? 'EN' : '中' }}
      </el-button>
    </div>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { switchLang } from './i18n'

function toggleLang() {
  switchLang()
  location.reload()
}
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #f5f5f5;
  color: #1a1a1a;
}

.nav-bar {
  display: flex;
  align-items: center;
}

.nav-bar .el-menu {
  flex: 1;
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
