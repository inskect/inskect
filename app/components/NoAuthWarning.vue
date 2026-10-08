<template>
  <UAlert
    color="warning"
    variant="subtle"
    icon="i-lucide-shield-alert"
    title="This server has no authentication"
    description="Anyone who can reach it can use the backoffice, including the Claude login. Keep it on a private network or behind your reverse proxy's login, or set INSKECT_AUTH=accounts to turn on user accounts."
  />
</template>
