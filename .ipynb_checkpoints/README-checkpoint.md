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

## Quick Start

```bash
git clone <this repo>
cd portal-server
docker compose up -d
```

Then visit `http://localhost:8000`. First run creates an admin account from the `ADMIN_USER`/`ADMIN_PASS` environment variables (defaults to `admin`/`admin` — **change this immediately**).

See [Getting Started](./data/_common/Information/getting_started.md) (also available in-app via the Wiki once running) for a tour of the interface.

## Requirements

- Docker + Docker Compose (recommended), or Python 3.11+ and the packages in `requirements.txt` if running bare-metal.
- That's it. No external database server required (SQLite by default; Postgres supported via `DATABASE_URL` env var if you want it).

## Project Layout

```
core_files/     The application itself — routing, auth, state, UI engine. This is the one thing
                every module depends on; it depends on nothing outside itself.
tools/          Lower-level utility modules, typically admin-facing (git integration, theme
                editor). Each folder is independently removable.
modules/        User-facing applications (wiki, chat/RP server, etc.). Each folder is
                independently removable and shares no direct code path with other modules.
data/           All runtime state — databases, uploaded files, module data. Not version
                controlled; back this up.
```

Dependency direction is strictly one-way: `core_files` → `tools`/`modules`. Modules and tools receive what they need from core through an injected `ENV` dict at load time (state accessors, template engine, theme resolver, etc.) rather than importing core internals directly. This is what makes a module folder genuinely deletable without breaking anything else — it never had a hard import path into the rest of the system to begin with.

## Adding a Module

Drop a folder into `modules/` containing a `{module_name}.py` with a FastAPI `router` and a `MODULE_META` dict. The server discovers it on next startup (or live reload, depending on your dev setup). See the developer documentation for the full contract (`init_module(env)`, available `ENV` keys, template context requirements).

## Philosophy

The short version is in [About](./data/_common/Information/about.md). The long version — the full architectural reasoning, the layered-security model, the accessibility commitments, and where this is headed — lives in `AI_Context.md` at the repository root, written as a living design document rather than static marketing copy.

## License

*(Fill in your chosen FOSS license here — GPLv3/AGPLv3 is worth considering specifically if you want to guarantee that hosted derivatives of this project also stay open, given the self-hosted-service nature of the software.)*

## Status

Pre-1.0. Core architecture (state system, module loading, interface manager, theming) is stable; expect breaking changes to module APIs before a 1.0 tag. Two reference modules (Wiki, RP Server) ship as working examples of the module contract.

## Contributing

This is currently maintained by a single developer as a personal project being opened up for others to use and build on. Issues and PRs are welcome — see `CONTRIBUTING.md` for coding style conventions used throughout the codebase (dense, single-responsibility functions; no build tooling; vanilla JS only; HTMX over client-side frameworks).
