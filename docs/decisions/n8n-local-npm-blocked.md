# Decision - n8n Local npm Installation Blocked

## Decision

Do not continue local Windows npm installation of n8n.

## Reason

The npm installation fails on the sqlite3 native dependency.

The install falls back to node-gyp rebuild.

node-gyp requires Visual Studio C++ Build Tools on Windows.

Installing Visual Studio C++ Build Tools for this stage adds unnecessary complexity.

## Evidence

- npm install -g n8n failed
- sqlite3 install failed
- prebuild-install timed out
- node-gyp rebuild failed
- Visual Studio C++ Build Tools were missing
- n8n command was left in a broken partial state

## Current Working Alternative

The Mecoria OS Notion Sync Runner already works directly from PowerShell.

Safe dry-run command:

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\notion_os_sync_runner.ps1

Safe apply command:

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\notion_os_sync_runner.ps1 -Apply

## Next Architecture

Use VPS self-hosted n8n later.

Do not use local Windows npm n8n for production.

Do not install Visual Studio C++ Build Tools only for n8n.

## Status

Local npm n8n path is blocked.

Mecoria OS Notion Sync Runner remains operational.

Next recommended work: continue Mecoria Media pipeline and return to n8n when VPS/self-hosting is ready.
