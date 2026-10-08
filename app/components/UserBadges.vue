<script setup lang="ts">
import type { UserRole, UserStatus } from '~~/shared/types/auth'

defineProps<{
  role: UserRole
  status: UserStatus
}>()
</script>

<template>
  <!-- Marked on the file like small stamps: the role, and a suspension in the critical ink. -->
  <span class="inline-flex flex-wrap gap-1.5">
    <span
      class="border px-1.5 font-display text-sm leading-tight font-bold tracking-wider uppercase"
      :class="role === 'admin' ? 'border-current text-brand-ink' : 'border-accented text-muted'"
    >{{ role }}</span>
    <span
      v-if="status === 'suspended'"
      class="border-2 border-current px-1.5 font-display text-sm leading-tight font-bold tracking-wider text-critical-ink uppercase"
    >suspended</span>
  </span>
</template>
