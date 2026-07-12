# RP Server Module

A collaborative roleplay, chat, and tabletop-adjacent room system. Multiple rooms, multiple personas per user, optional AI-driven narration or character play, and a set of built-in tools for running a game session (dice, name generation, character sheets).

## Basic Concepts

- **Room** — a chat space. Public rooms are visible and joinable by anyone; private rooms are invite-only, managed by their owner.
- **Persona** — a display identity you post as. You always have an implicit persona matching your account username, and can create as many additional named personas as you like (a player might have one persona per character they play, for instance).
- **You can only be in one room at a time per browser session**, but your active room and persona are both saved to your account, so switching devices picks up where you left off.

## Getting Started

Opening the module shows three areas:
- **Left sidebar** — room list, persona list, and buttons for Options, Room Settings, Persona Settings, and RP Tools.
- **Center** — the current room's background/stage image.
- **Right panel** — the chat itself, with the room name and your active persona shown at the top.

### Joining or Creating a Room

Click a room in the left sidebar to join it. To create a new room, type a name in the box below the room list and hit the `+` button — you become that room's owner automatically, with a private room type by default.

### Switching Personas

Click a persona in the left sidebar list to make it active — everything you post from then on uses that persona's name and (if set) avatar. Your own username is always available as an implicit persona at the top of the list.

To create a new persona, open **Persona Settings** and use the small form at the bottom of that panel.

## Room Settings (owner or admin/moderator only)

Opened via the **Room Settings** button in the sidebar:

- **Title** — the display name for the room.
- **Mode** — General Chat, Visual Novel, or TTRPG/D&D. This is a hint for AI narration style, not a hard restriction on features.
- **Display Names** — whether the chat shows each message's persona name, the underlying account username, or both.
- **Show Timestamps** — whether each message shows a time.
- **Setting / World** — free-text world/setting description and detail, used as context if AI narration is enabled for the room.
- **Members** — for private rooms, an explicit invite list by username. Public rooms have no membership list; anyone can join.
- **Background Image** — upload an image to set as the room's stage background, visible to everyone in the room. Use the Remove button to clear it back to blank.
- **AI Settings** — link to the full AI configuration panel (see below), if the AI extension is installed.

## Personas In Depth

Each persona has:
- **Name** — must be unique among your own personas (two different users can each have a persona with the same name).
- **Description** — free text describing the character; also used as context if this persona is played by AI.
- **Sprite** — an avatar image shown next to their messages in chat.
- **AI toggle** — mark whether this persona is available for AI character-mode narration in rooms that enable it.

Open a persona's settings with the pencil icon next to it in the sidebar list, or through the full **Persona Settings** panel for a larger editing view.

## Messages

- Type in the input box at the bottom of the chat panel and press the Send button, or `Ctrl+Enter`.
- Hover a message to reveal **Copy** (copies the raw markdown), **Edit** (your own messages only), and **Delete** (your own messages, or any message if you own the room or are a moderator/admin) actions.
- Message content supports the same markdown formatting as the wiki (bold, italic, code, links, etc.) — it's rendered the same way.
- A scroll-to-bottom button appears automatically if you've scrolled up in a busy chat.

## AI Narration (optional)

If the AI extension is installed, each room can independently enable one of two modes:

- **Character mode** — the AI plays one specific persona you select, staying fully in that character based on its description.
- **DM/Narrator mode** — the AI describes environment, mood, and minor background characters, without ever speaking or acting for the actual player characters. It's deliberately restrained to atmosphere and background events, not plot-driving — the intent is to support the scene, not take it over.

Configuration (via the AI settings panel, reached from the AI status button in the sidebar):
- **Model backend** — an Ollama-compatible endpoint URL and model name. This is designed for locally-hosted models first; there's no built-in dependency on any external AI API.
- **Trigger** — when the AI responds: every N messages, a random probability per message, when a message contains a specific keyword, or only when manually triggered (typing `@ai`, `@dm`, or `@gm`, or using the "Trigger Now" button).
- **Scenario Block** — a persistent piece of context always included, useful for an overall premise that shouldn't be forgotten as the conversation scrolls.
- **History compression** — older messages beyond a configurable depth are automatically summarized into a running digest rather than dropped, so long-running scenes don't lose earlier context entirely, without needing to feed the entire history to the model every time.

The AI status button in the sidebar shows the room's current mode at a glance ("AI: Off", "AI: DM", or "AI: {persona name}") and opens the full settings panel with one click.

## RP Tools

A menu of small utilities for running a session, opened via the **RP Tools** button in the sidebar.

### Dice Roller
Standard `NdM+K` notation — `2d6+3` rolls two six-sided dice and adds 3, `1d20` rolls a single d20, etc. A row of quick buttons covers the common dice sizes. Every roll is logged with its individual die results and total, newest at the top.

### Name Generator
Pick a category (fantasy male, fantasy female, sci-fi, or surname) and generate a batch of eight names at once. Click the copy icon next to any name to copy it to your clipboard.

### Character Sheets
A generalized, template-driven sheet system — not locked to any one game system. A sheet template is a simple list of fields (text or multi-line text), and the server ships with a generic template covering concept, appearance, personality, background, stats, inventory, and notes. Pick a persona and a template, fill in the fields, and save — each persona can have one saved sheet per template.

Because templates are just JSON files, adding a new one (for a specific game system's stat block, or a non-character sheet like a location or faction writeup for building out a setting) doesn't require any code changes — drop a new template file in alongside the default and it becomes selectable. If you want structured setting content (locations, factions, timelines) rather than character sheets specifically, the same templating mechanism works for that too — just point a new template at the kind of thing you want to track, and it becomes another sheet type in the picker.

## Options (your personal settings, not room-wide)

Opened via the **Options** button:

- **Notifications** — per-room, whether you get a push notification when someone posts in that room while you're not actively viewing it. Requires push notifications to be configured on the server and permitted by your browser.
- **Appearance** — your personal message-bubble colors and whether new messages auto-scroll the chat to the bottom.

These are yours alone — they don't affect what other people in a shared room see.
