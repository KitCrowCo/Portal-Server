# About This Server

## What This Is

This is a self-hosted, modular personal server — a single unified entry point to your own small digital ecosystem. Instead of juggling a dozen different apps and accounts for a dozen different services, everything lives behind one login, on hardware you control.

It's built around a simple idea: a small number of trusted people (usually a household, sometimes a small group of friends running a game together, sometimes just one person) should be able to run their own private corner of the internet without needing to be a systems administrator, and without handing their data to a company whose business model depends on collecting it.

## What It's Not

- It's not a SaaS product. There's no company behind this collecting your usage data, no subscription, no account you can be locked out of by a third party.
- It's not trying to replace the entire internet for you. You can still use whatever other services you want — this gives you a *choice* to move things you care about onto something you own, not a mandate to cut yourself off from everything else.
- It's not "free as in ads." There is no telemetry. There is no hidden data collection. This isn't a policy promise — the architecture itself doesn't have a mechanism to phone home.

## Why It's Built This Way

The short version: most digital infrastructure today extracts value from the people using it — through surveillance, lock-in, and manufactured obsolescence. This project is an attempt at a working alternative, not just a complaint about the problem.

A few concrete commitments that follow from that:

- **Your data stays on your server.** Not "unless you opt out" — there's no path for it to leave unless you explicitly set one up (e.g., you choose to connect an outside service).
- **No corporate dependency where an open alternative exists.** Local fonts, local JavaScript libraries, local database. If it can run without the internet, it does.
- **Accessible by design, not as an afterthought.** Every feature should work the same whether you're using a mouse, a touchscreen, or a keyboard alone. This isn't just a nice-to-have — treating people who can't use a mouse, or can't see a screen, as an edge case is a form of discrimination baked into a lot of software, intentionally or not.
- **Simple over impressive.** A simpler system with fewer moving parts is more secure and more maintainable than a complex one with more "features." This shows up as a preference for boring, well-understood technology (SQLite, server-rendered HTML) over the trendier alternative.

## Who Runs This

This particular server is run by an individual (or small group — check with whoever gave you access) for personal or household use, not as a commercial offering. If you were invited to use it, that's a deliberate choice by the owner to extend access to you — treat it accordingly.

## Where This Is Going

The long-term goal is for this kind of server to be genuinely deploy-able by anyone, not just people with a technical background — an eventual "install and go" experience with no command line required. Beyond that, the roadmap includes things like offline-first operation, mesh networking between personal servers, and stronger encryption guarantees, so that "sovereign" doesn't just mean "not in the cloud" but actually means resistant to the network itself failing or being compromised around you.

None of that is required to use the server today — everything above describes the direction, not a precondition.

## Questions or Problems

If you're the person operating this server: check the project's README and developer documentation for troubleshooting, module installation, and configuration details. If you're a guest user experiencing a problem, the person who invited you is your first point of contact — they control the server, not any outside party.
