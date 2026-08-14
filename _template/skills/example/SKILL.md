---
name: example
description: Use when working with <service> — describe here the concrete tasks that trigger this skill (downloading assets, generating, checking the account) and the terms the user will actually say. This line decides whether the skill loads, so write it thinking about what the user will say, not what the plugin is called.
---

# <Service>

One or two lines: what the service is and what this plugin solves.

Clarify from the start how the work is split, because it's almost never all
on one side:

- **MCP (`<service>_*`)** — what's done via the API.
- **Browser** — what can only be done in the UI.

## Precondition: authentication

**Before the first operation of each session, call `<service>_auth_status`.**
It's local, free, and doesn't touch the network.

| Result | What to do |
|---|---|
| `valid: true` | continue |
| `valid: false` (renewable) | continue; it renews itself |
| `valid: false` (not renewable) | **stop and ask the user to renew** |
| tool fails with `AUTHENTICATION:` | same |

Ask for renewal with concrete instructions: what to export, from where,
with what name, and where to put it. **Never** retry a tool that failed on
authentication, and don't try others "to see if they work": a repeated 401
is what gets an account flagged.

## Behavior rules

Adapt this list, but don't delete it — it's the reason the plugin is safe:

1. **Slow, paced requests.** No bursts, no fast retries, no parallelism.
2. **Verify by measuring** (`ffprobe`, `astats`), not by impression. The
   numbers go in the report.
3. **Don't evade a block.** A 403 or a CAPTCHA is the provider's decision.
4. **Confirm before spending** credits or any irreversible action.
5. **Verify what you deliver** instead of trusting the file name.
6. **Never delete anything belonging to the user.**

## Flows

Step-by-step for the typical operations. Include what can only be learned
by doing: how long each thing takes, what intermediate states the UI shows,
what fails and why.

## API map

Base URL, authentication, and the endpoint table with what each one
returns. Note the traps: fields that exist but lie, endpoints that deny
something on purpose, real limits.

## Packs

If the plugin supports project-specific shortcuts, explain how they're
activated (`<SERVICE>_PACK`) and what they add. **The core works without
any pack**: if a tool only works with a pack, it's badly designed.
