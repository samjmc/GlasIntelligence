<template>
  <!-- Shown by the process pages when the backend answers 404 for the project or simulation,
       or when /process/new is opened with nothing to build -->
  <div class="project-unavailable" role="alert">
    <h2 class="unavailable-title">{{ title }}</h2>
    <router-link :to="linkTo" class="unavailable-link">{{ linkText }}</router-link>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: 'This project is no longer available.' },
  linkTo: { type: String, default: '/dashboard' },
  linkText: { type: String, default: 'Back to dashboard' },
})
</script>

<style scoped>
.project-unavailable {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 24px;
  text-align: center;
}

.unavailable-title {
  font-size: 18px;
  font-weight: 700;
  color: #000;
}

.unavailable-link {
  margin-top: 8px;
  padding: 8px 16px;
  border-radius: 4px;
  background: #000;
  color: #FFF;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
}
</style>
