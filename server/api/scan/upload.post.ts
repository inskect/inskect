// A skill uploaded with the scan: the file and the scan's options go on to the API.
export default defineEventHandler(async (event) => {
  const parts = await readMultipartFormData(event)
  const file = parts?.find(part => part.name === 'file' && part.filename)
  if (!file) {
    throw createError({ statusCode: 400, statusMessage: 'Choose a file to upload' })
  }
  let options: ScanOptionsBody
  try {
    options = JSON.parse(parts?.find(part => part.name === 'options')?.data.toString('utf8') || '{}')
  } catch {
    throw createError({ statusCode: 400, statusMessage: 'The scan options aren’t valid' })
  }

  const form = new FormData()
  form.append('file', new Blob([new Uint8Array(file.data)], { type: file.type ?? 'application/octet-stream' }), file.filename)
  form.append('options', JSON.stringify(toApiScanOptions(options)))
  return await backendFetch<{ id: string, status: string }>(event, '/scan/upload', {
    method: 'POST',
    body: form,
    fallbackMessage: 'Failed to queue scan'
  })
})
