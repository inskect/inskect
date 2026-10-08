// Where to go after signing in: the page that sent the visitor to sign in, if it's one of ours.
export function useAuthRedirect() {
  const route = useRoute()
  return computed(() => localPath(route.query.redirect) ?? '/')
}
