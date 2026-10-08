// The models skillspector knows per provider, for the scan form's model picker. They change only
// with the API's skillspector version, so they're cached for an hour (a failed fetch isn't).
export default defineCachedEventHandler(async (event) => {
  return await backendFetch<Record<string, { default: string | null, models: string[] }>>(event, '/models', {
    fallbackMessage: 'Failed to fetch the model list'
  })
}, {
  name: 'models',
  getKey: () => 'models',
  maxAge: 60 * 60
})
