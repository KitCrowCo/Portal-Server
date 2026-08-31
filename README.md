# Portal Server

A self-hosted, modular personal server — a single unified entry point to a small private digital ecosystem. Built for households, small groups, and individuals who want their own corner of the internet without becoming a full-time systems administrator or handing their data to a company.

No telemetry. No accounts you don't control. No forced obsolescence. Runs on hardware you own.

---

## What It Does

- **One login, many capabilities.** Modules (a wiki, a roleplay/chat server, whatever else is installed) all live behind a single portal, each opening as its own tab.
- **Works the same everywhere.** No separate mobile app, no separate desktop client — the same server renders correctly and functions identically on phone, tablet, and desktop, including as an installable PWA.
- **Server-sovereign state.** All meaningful state lives on the server, not in the browser. Close the tab, come back a week later on a different device, and you're exactly where you left off.
- **Drop-in modules.** Adding a capability is a folder drop into `modules/` or `tools/` — no build step, no package manager dance.
- **Cascading, swappable themes.** Server default → module default → your personal theme → your per-module override. Change look and feel without touching a single line of module code.

## Install

To install the Core Server plus the standard reference modules (Wiki, RP Server, Git Manager) in one step:

```bash
git clone [https://git.kitcrowco.com/KitCrowCo/Portal_Server.git](https://git.kitcrowco.com/KitCrowCo/Portal_Server.git)
cd Portal_Server
docker compose up -d --build
```

Then visit `http://localhost:8000`. First run creates an admin account from the `ADMIN_USER`/`ADMIN_PASS` environment variables (defaults to `admin`/`admin` — **change this immediately**, either before first boot via your `docker-compose.yml` or in Control Panel right after logging in).

See [Getting Started](https://www.google.com/search?q=./data/_common/Information/getting_started.md) for a tour of the interface.

## Why Multiple Repos?

Core (`core_files/`) and every module/tool are versioned as **separate git repositories**. This is what makes a module genuinely deletable, independently upgradable, and independently forkable.

During standard installation (`docker compose up --build`), the Dockerfile automatically clones the standard reference modules for you. If you want to customize or develop locally, simply run `git clone <repo> modules/<name>` on your host machine before building; the Docker builder will detect your local copies and use them instead.

## Requirements

- Docker + Docker Compose (recommended), or Python 3.11+ and the packages in `requirements.txt` if running bare-metal.
- That's it. No external database server required (SQLite by default; Postgres supported via `DATABASE_URL` env var if you want it).

## Project Layout

```
core_files/     The application itself — routing, auth, state, UI engine. This is the one thing every module depends on; it depends on nothing outside itself.
tools/          Lower-level utility modules, typically admin-facing (git integration, theme editor). Each folder is independently removable.
modules/        User-facing applications (wiki, chat/RP server, etc.). Each folder is independently removable and shares no direct code path with other modules.
data/           All runtime state — databases, uploaded files, module data. Not version controlled; back this up.
```

Dependency direction is strictly one-way: `core_files` → `tools`/`modules`. Modules and tools receive what they need from core through an injected `ENV` dict at load time (state accessors, template engine, theme resolver, etc.) rather than importing core internals directly.

## Adding a Module

Drop a folder into `modules/` containing a `{module_name}.py` with a FastAPI `router` and a `MODULE_META` dict. The server discovers it on next startup. See the developer documentation for the full contract (`init_module(env)`, available `ENV` keys, template context requirements).

## Adding AI Tools (optional, separately licensed)

The AI Tools suite (chat, knowledge base, pipeline builder, image generation) is a separate module/tool pair under different license terms than core - see the Economic Framework section below before enabling it commercially.

To include them, clone them into your local directories before building the container:

```bash
git clone [https://git.kitcrowco.com/KitCrowCo/Portal-Server_Module_AI_Tools.git](https://git.kitcrowco.com/KitCrowCo/Portal-Server_Module_AI_Tools.git) modules/ai_tools
git clone [https://git.kitcrowco.com/KitCrowCo/Portal-Server_Tool_AI_Manager.git](https://git.kitcrowco.com/KitCrowCo/Portal-Server_Tool_AI_Manager.git) tools/ai_manager
docker compose up -d --build
```

## License

- **Core (`core_files/`)** — AGPLv3. This matters specifically because this is self-hostable server software — AGPL closes the loophole in GPL where someone could run a modified version as a network service without ever distributing the modified source.
- **AI Tools module + ai_manager tool** — Polyform Noncommercial 1.0.0. Free for personal, academic, and non-commercial use. Commercial use requires FSEP registration - see below.
- Reference modules (Wiki, RP Server) and other tools — AGPLv3, matching core, unless that individual repo's own `LICENSE` says otherwise.

## Economic Framework: Fair-Share Economic Protocol (FSEP)

Portal Server's AI Tools and the sDAG architecture are released under a non-commercial license (Polyform Noncommercial). Commercial use is intended to be made available exclusively through the **Fair-Share Economic Protocol (FSEP)** - a proposed framework that caps individual commercial earnings from this work at a level tied to independent global economic data, redirecting excess into a shared pool rather than unlimited private accumulation.

FSEP is a staged, honestly-incomplete proposal, not a finished legal instrument - see the full draft for what's actually solved versus openly unsolved. The author has submitted it to the Software Freedom Law Center for review and is not a lawyer; if you have relevant legal, economic, or governance-design expertise and want to help make this real, that input is genuinely wanted; ideally something can be worked out even if talks fail - this is intended to seriously try and find ways to make it work, or at least identify hard specific problems to solve, not simply die on arrival for lack of engagement.

- [**FSEP proposal (Zenodo)**](https://doi.org/10.5281/zenodo.22152670)
- [**sDAG architecture whitepaper (Zenodo)**](https://doi.org/10.5281/zenodo.22103362)
- [**Escaping the Paradigm — on AI cognitive architecture and why this shouldn't be a 1:1 labor replacement (Zenodo)**](https://doi.org/10.5281/zenodo.22117566)

Commercial use of the AI Tools codebase is exclusively available via FSEP, if and when a working agreement is finalized.

## Support This Project

This project is self funded and any support is appreciated and can be through this square link [Donate](https://square.link/u/1e32E3gY)  - a joint effort spanning this codebase and my own similar work as well as Mephie's events and advocacy work centering women and marginalized/queer people in games and media.

## Philosophy

The short version is in [About](./data/_common/Information/about.md). The long version — the full architectural reasoning, the layered-security model, the accessibility commitments, and where this is headed — is written as a living design document rather than static marketing copy - This will be in the core files at a later update.

## Status

Pre-1.0. Core architecture (state system, module loading, interface manager, theming) is stable; expect breaking changes to module APIs before a 1.0 tag. Two reference modules (Wiki, RP Server) ship as working examples of the modules.

## Contributing

This is a personal project, actively maintained by one person, and not currently seeking contributors or co-maintainers. You're free to fork it, modify it, and run your own version under the terms of its license — that's the point of it being open source. Issues reporting genuine bugs are welcome; unsolicited large feature PRs are unlikely to be merged, since the project has a specific architectural direction that isn't a democratic process.