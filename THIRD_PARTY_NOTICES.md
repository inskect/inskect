# Third-party notices

Inskect is licensed under the [AGPL-3.0](./LICENSE). It isn't distributed with the code of the
projects below: they're installed when it's built (`uv sync`, `pnpm install`), each under its own
license, which its package carries (Python packages in their `*.dist-info/licenses/`, npm packages
in their folder). The Docker images keep those files.

Every license below is compatible with the AGPL-3.0, and CI checks the whole dependency tree
([CONTRIBUTING.md](./CONTRIBUTING.md#checks)).

## The scanning engine

**[skillspector](https://github.com/NVIDIA/skillspector)**, by NVIDIA, under the
[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0). Inskect runs it as a library,
at the version pinned in [`backend/pyproject.toml`](./backend/pyproject.toml). Inskect is not
affiliated with or endorsed by NVIDIA.

## Scan service (`backend/`)

| Package | License |
|---|---|
| [FastAPI](https://github.com/fastapi/fastapi) | MIT |
| [Uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause |
| [pydantic-settings](https://github.com/pydantic/pydantic-settings) | MIT |
| [psycopg](https://github.com/psycopg/psycopg), psycopg-pool | LGPL-3.0-only |
| [cryptography](https://github.com/pyca/cryptography) | Apache-2.0 or BSD-3-Clause |
| [PyYAML](https://github.com/yaml/pyyaml) | MIT |
| [python-multipart](https://github.com/Kludex/python-multipart) | Apache-2.0 |
| [HTTPX](https://github.com/encode/httpx) | BSD-3-Clause |

## Web app

| Package | License |
|---|---|
| [Nuxt](https://github.com/nuxt/nuxt) | MIT |
| [Nuxt UI](https://github.com/nuxt/ui) | MIT |
| [Nuxt Fonts](https://github.com/nuxt/fonts) | MIT |
| [Lucide icons](https://github.com/lucide-icons/lucide) (`@iconify-json/lucide`) | ISC |

Their own dependencies are under permissive licenses (MIT, Apache-2.0, ISC, BSD, BlueOak, 0BSD), or
MPL-2.0 for lightningcss, a build tool. Two packages declare no license in their metadata:
`vaul-vue`, MIT in [its repository](https://github.com/Elliot-Alexander/vaul-vue), and this project
itself (`inskect`), AGPL-3.0-only. Fonts are served from the app (Archivo, JetBrains Mono: SIL Open
Font License 1.1).
