const url = process.argv[2]

try {
  const response = await fetch(url, { signal: AbortSignal.timeout(2000) })
  process.exit(response.ok ? 0 : 1)
} catch {
  process.exit(1)
}
