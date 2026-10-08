export default defineAppConfig({
  site: {
    name: 'Inskect',
    description: 'Scan agent skills for vulnerabilities before you install them.',
    // The link preview image, 1200×630, rendered by scripts/og-image/render.py.
    ogImage: {
      path: '/og-inskect.png',
      alt: 'Inskect: inspect a skill before it runs. An inspection report stamped Rejected.'
    },
    repo: 'inskect/inskect',
    scannerRepo: 'NVIDIA/skillspector'
  },
  ui: {
    colors: {
      primary: 'insp',
      neutral: 'graphite',
      success: 'green',
      warning: 'amber',
      error: 'red'
    },
    button: {
      slots: {
        base: 'cursor-pointer rounded-none font-semibold'
      },
      // The call to action: inspection blue with white text, in both themes.
      compoundVariants: [{
        color: 'primary',
        variant: 'solid',
        class: 'bg-brand text-white hover:bg-insp-700 active:bg-insp-700 disabled:bg-brand aria-disabled:bg-brand focus-visible:outline-brand'
      }]
    },
    // A card is a sheet: square, under a heavier ink rule.
    card: {
      slots: {
        root: 'rounded-none border-t-2 border-inverted',
        body: 'p-5 sm:p-6'
      }
    },
    input: {
      slots: {
        base: 'rounded-none'
      }
    },
    link: {
      base: 'cursor-pointer'
    },
    select: {
      slots: {
        base: 'cursor-pointer',
        item: 'cursor-pointer'
      }
    },
    selectMenu: {
      slots: {
        base: 'cursor-pointer',
        item: 'cursor-pointer'
      }
    },
    // The field itself is typed in; its toggle and items are clicked.
    inputMenu: {
      slots: {
        trailing: 'cursor-pointer',
        item: 'cursor-pointer'
      }
    },
    dropdownMenu: {
      slots: {
        item: 'cursor-pointer'
      }
    },
    checkbox: {
      slots: {
        base: 'cursor-pointer',
        label: 'cursor-pointer'
      }
    },
    switch: {
      slots: {
        base: 'cursor-pointer rounded-none',
        thumb: 'rounded-none',
        label: 'cursor-pointer'
      }
    }
  }
})
