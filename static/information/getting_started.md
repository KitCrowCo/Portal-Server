# Getting Started

This page covers first login, the basic layout, and how to get comfortable with the server. If you want the philosophy behind why it's built this way, see [[Information/about|About This Server]] instead.

## First Login

The first account created is always an admin account (set via `ADMIN_USER`/`ADMIN_PASS` at first startup, or defaulting to `admin`/`admin` — change this immediately if you haven't already). Log in at the root address of your server.

Once logged in you'll see the dashboard. This is your home base — it lists every Module you have access to as a card. Click a card to open that module in a tab.

## The Basic Layout

- **Left sidebar** — your account info, module launcher shortcuts, and logout. Slides in from the left; toggle it with the arrow button.
- **Top bar** — your open tabs. Click `+` to open a new tab (defaults to the launcher/dashboard). Tabs persist across logins on the same account — closing your browser doesn't lose your place.
- **Bottom bar (Input Bridge)** — a universal action toolbar (copy, paste, undo, arrow keys, etc.) that works the same whether you're on a phone, a tablet, or a desktop with a broken mouse. It's collapsed by default; tap the `⌃ Bridge` button to expand it. This exists so that no single input method is required to fully use the server — if a module needs "select all" or "undo" and your device can't produce that keystroke normally, the bridge can.
- **Control Panel** — gear icon in the sidebar (admins only, mostly). Account settings, appearance/theme, and — if you're an admin — user management and module access control live here.

## Modules vs. Tools

- **Modules** are the things you actually use day-to-day: Wiki, RP Server, whatever else is installed. Each opens as its own tab.
- **Tools** are lower-level utilities, usually admin-facing (Git Manager, Theme Designer). They tend to support modules rather than being used directly for content.

Neither requires installation in the traditional sense — an admin drops a folder into the right directory and the server picks it up automatically on next restart (or live, depending on configuration).

## Appearance / Themes

Themes cascade in four layers, each optional and each overriding the one before it:

1. **Server default** — set by an admin, applies to everyone.
2. **Module default** — a module (or its admin) can set a different baseline just for that module.
3. **Your personal theme** — set in Control Panel → Appearance, applies to every module for you specifically.
4. **Your per-module override** — set via the Theme Designer tool (if installed) or a module's own appearance settings, applies only to you, only in that one module.

You never have to touch this — the server ships with a dark theme ("Obsidian Sapphire") and a light theme ("Japanese Zen") and you can just pick one in Control Panel → Appearance and move on. The layering exists for people who want to go further, not as a requirement.

## Mobile / PWA

The server is designed to work identically on mobile and desktop — there's no separate "mobile version." On a phone, you can add it to your home screen as an installable app (PWA) for a native-app-like experience, including push notifications if configured.

## Getting Help

If something in a module is unclear, most modules include their own help text near the feature in question (look for a `?` icon). For server-level administration questions, see the Control Panel sections directly — most have inline explanations.

If you're technically inclined and want to understand *why* things work the way they do, or you're thinking about writing your own module, see [[Information/about|About This Server]] and the project's developer documentation.
