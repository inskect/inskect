<script setup lang="ts">
const id = useRoute().params.id as string
</script>

<template>
  <ScanResult
    :api-base="`/api/scan/${id}`"
    :scan-id="id"
  />
</template>
