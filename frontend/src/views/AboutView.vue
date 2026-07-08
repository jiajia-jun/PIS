<template>
  <div class="about-page">
    <!-- 项目介绍 -->
    <el-card class="about-card" shadow="hover">
      <h2 class="section-title">{{ $t('about.intro_title') }}</h2>
      <p class="section-text">{{ $t('about.intro_p1') }}</p>
      <p class="section-text">{{ $t('about.intro_algo') }}</p>
      <p class="section-text">{{ $t('about.intro_data') }}</p>
      <p class="section-text">{{ $t('about.intro_p2') }}</p>
    </el-card>

    <!-- 技术栈 -->
    <el-card class="about-card" shadow="hover">
      <h2 class="section-title">{{ $t('about.tech_title') }}</h2>
      <div class="tech-tags">
        <el-tag v-for="tech in techs" :key="tech" size="large" effect="plain">{{ tech }}</el-tag>
      </div>
    </el-card>

    <!-- 团队成员 -->
    <el-card class="about-card" shadow="hover">
      <h2 class="section-title">{{ $t('about.team_title') }}</h2>
      <div class="team-grid">
        <div v-for="m in members" :key="m.name" class="team-item">
          <el-avatar :size="56" class="team-avatar">{{ m.name.charAt(0) }}</el-avatar>
          <div class="team-name">{{ m.name }}</div>
          <div class="team-role">{{ m.role }}</div>
        </div>
      </div>
    </el-card>

    <!-- 联系方式 -->
    <el-card class="about-card" shadow="hover">
      <h2 class="section-title">{{ $t('about.contact_title') }}</h2>
      <div class="contact-item">
        <el-icon class="contact-icon"><Message /></el-icon>
        <span>{{ $t('about.contact_value') }}</span>
      </div>
      <div class="contact-item">
        <el-icon class="contact-icon"><Link /></el-icon>
        <a class="contact-link" :href="$t('about.github_url')" target="_blank" rel="noopener">{{ $t('about.github_label') }}</a>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { Message, Link } from '@element-plus/icons-vue'

const techs = ['Go', 'Gin', 'GORM', 'MySQL', 'zap', 'Vue 3', 'Vite', 'Element Plus', 'Vue Router', 'Vue I18n', 'OpenCV', 'Python']

const members = [
  { name: '成员A', role: '后端组' },
  { name: '成员B', role: '数据分析组' },
  { name: '成员C', role: '算法组' },
  { name: '成员D', role: '算法组' },
  { name: '成员E', role: '算法组' },
]
</script>

<style scoped>
.about-page {
  max-width: 700px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.about-card {
  border-radius: 12px;
  padding: 8px;
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 16px 0;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-light);
}

.section-text {
  font-size: 15px;
  line-height: 1.8;
  color: var(--text-secondary);
  margin: 0 0 12px 0;
}

.section-text:last-child {
  margin-bottom: 0;
}

/* 技术栈标签 */
.tech-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

/* 团队网格 */
.team-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 20px;
  text-align: center;
}

.team-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.team-avatar {
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-light) 100%);
  color: #fff;
  font-size: 22px;
  font-weight: 600;
}

.team-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.team-role {
  font-size: 12px;
  color: var(--text-hint);
  background: var(--bg-tag);
  padding: 2px 10px;
  border-radius: 10px;
}

/* 联系方式 */
.contact-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  color: var(--text-secondary);
}

.contact-icon {
  color: var(--accent);
  font-size: 18px;
  flex-shrink: 0;
}

.contact-link {
  color: var(--accent);
  text-decoration: none;
}

.contact-link:hover {
  text-decoration: underline;
}

@media (max-width: 768px) {
  .about-page {
    padding: 0;
  }

  .team-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
  }
}
</style>
