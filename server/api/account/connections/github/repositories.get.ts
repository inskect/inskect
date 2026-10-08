// The repositories the user's GitHub connection reads, to pick one to scan (ScanForm's picker).
export default defineEventHandler(async (event) => {
  return await backendFetch(event, '/account/connections/github/repositories', {
    fallbackMessage: 'Couldn’t list your GitHub repositories'
  })
})
