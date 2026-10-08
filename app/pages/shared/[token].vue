<script setup lang="ts">
// A result someone shared: read-only, and open without signing in (middleware/auth.global.ts).
const token = useRoute().params.token as string
</script>

<template>
  <ScanResult :api-base="`/api/shared/${encodeURIComponent(token)}`" />
</template>
