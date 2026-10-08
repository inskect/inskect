import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// This app's own files, wherever it's built from: its own checkout, or another app that extends it
// as a Nuxt layer (docs/EXTENDING.md#layering-the-web-app), where `~` is that app's directory.
const here = (path: string) => fileURLToPath(new URL(path, import.meta.url))

export default defineNuxtConfig({
  modules: [
    // Linting this repository: a development dependency, which an app extending this one doesn't have.
    ...(existsSync(here('./node_modules/@nuxt/eslint')) ? ['@nuxt/eslint'] : []),
    '@nuxt/ui',
    '@nuxt/fonts'
  ],

  devtools: {
    enabled: true
  },

  app: {
    head: {
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
        { rel: 'icon', href: '/favicon.ico', sizes: '48x48' },
        { rel: 'apple-touch-icon', href: '/apple-touch-icon.png' }
      ]
    }
  },

  css: [here('./app/assets/css/main.css')],

  runtimeConfig: {
    apiBase: process.env.NUXT_API_BASE || 'http://localhost:8000',
    trustProxy: false,
    // The Content-Security-Policy reported rather than enforced (server/middleware/security-headers.ts),
    // so what it would block shows in the logs before it's enforced: NUXT_CSP_REPORT_ONLY=true.
    cspReportOnly: false,
    // Origins the browser may send requests to besides this server, e.g. an analytics or storage
    // service a build adds: NUXT_CSP_CONNECT_SRC='["https://example.com"]'. None by default.
    cspConnectSrc: [] as string[],
    public: {
      // This server's public address, e.g. https://inskect.example.com, for the link preview
      // image's absolute URL (useSiteUrl). Unset, it's the address each page was requested at.
      siteUrl: '',
      // Where this server's source code is offered to its users, as the AGPL-3.0 requires (section
      // 13): your own repository if you run a modified version. Unset, this project's.
      sourceUrl: ''
    }
  },

  routeRules: {
    // The link preview image (app.config.ts): cached a year, so it's renamed when it changes.
    '/og-inskect.png': { headers: { 'cache-control': 'public, max-age=31536000, immutable' } }
  },

  compatibilityDate: '2026-09-03',

  vite: {
    server: {
      allowedHosts: process.env.NUXT_ALLOWED_HOST ? [process.env.NUXT_ALLOWED_HOST] : []
    }
  },

  hooks: {
    // The home page renders the scanner or the landing page (pages/index.vue), each a lazy chunk.
    // Nuxt would prefetch both, so the landing page would still download the scanner, which is what
    // splitting them avoids; the one rendered is preloaded anyway.
    'build:manifest': (manifest) => {
      for (const entry of Object.values(manifest)) {
        entry.dynamicImports = entry.dynamicImports?.filter(id => !/(^|\/)components\/(HomeScanner|LandingPage)\.vue$/.test(id))
      }
    }
  },

  eslint: {
    config: {
      stylistic: {
        commaDangle: 'never',
        braceStyle: '1tbs'
      }
    }
  },

  fonts: {
    defaults: {
      weights: [400, 500, 600, 700],
      styles: ['normal']
    }
  },

  // Every icon the app uses, found in its source, ships with it: none is fetched at runtime from
  // /api/_nuxt_icon.
  icon: {
    clientBundle: {
      scan: true
    }
  }
})
