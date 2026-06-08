# wb

Writer's Block is a terminal-native drafting tool for writing long work one
proposition at a time.

The app is generic. It does not ship with any book plan, manuscript, or private
writing material.

A proposition is complete when the draft body below the `wb` marker reaches the
configured minimum character count.

## Install

```bash
./install.sh
```

Or install from GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/ryangerardwilson/wb/main/install.sh | bash
```

The installer keeps the internal runtime under `~/.wb/` and publishes the
user-facing command at `~/.local/bin/wb`.

If `~/.local/bin` is not already on your `PATH`, add it once to `~/.bashrc` and
reload:

```bash
export PATH="$HOME/.local/bin:$PATH"
source ~/.bashrc
```

## Usage

```bash
wb help
wb version
wb list
wb upgrade
```

Create a generic book structure file:

```bash
wb init
wb init ./structure.json
```

Write the next proposition with explicit paths:

```bash
wb write ./structure.json drafts ./drafts
wb write ./structure.json drafts ./drafts first
```

Save a named preset and inspect progress from any directory:

```bash
wb preset save "an eye for an eye" structure /path/to/structure.json drafts /path/to/drafts
wb list
wb use "an eye for an eye"
wb use "an eye for an eye" status
wb use "an eye for an eye" list
wb use "an eye for an eye" show
```

Export completed draft bodies:

```bash
wb export ./structure.json drafts ./drafts to manuscript.md
wb export ./structure.json drafts ./drafts all
wb use "an eye for an eye" export to manuscript.md
```

Edit the app config directly:

```bash
wb config
```

## Config

App config is XDG compliant:

```text
$XDG_CONFIG_HOME/wb/config.json
~/.config/wb/config.json
```

The app config stores generic defaults and named presets:

```json
{
  "extension": "md",
  "min_chars": 500,
  "presets": {
    "an eye for an eye": {
      "structure": "/path/to/structure.json",
      "drafts": "/path/to/drafts"
    }
  }
}
```

Book-specific structure belongs in a separate JSON file. That file defines the
title, chapters, propositions, and optional per-book settings:

```json
{
  "title": "Untitled Book",
  "settings": {
    "extension": "md",
    "min_chars": 500
  },
  "chapters": [
    {
      "title": "Chapter One",
      "propositions": [
        "State the first proposition this chapter needs to prove."
      ]
    }
  ]
}
```

Drafts are plain Markdown files under the drafts directory passed on the command
line or stored in the preset.

Editor resolution follows the workspace contract:

1. `$VISUAL`
2. `$EDITOR`
3. `vim`

When `wb` launches Vim or Neovim, it sets prose wrapping at `79` characters with
a `79` column marker. Draft files keep that as a plain comment rather than a
Vim option string.

## Release

This repo follows the workspace CLI contract:

```bash
./push_release_upgrade.sh
```

That script pushes the current branch, tags the next release, waits for the
GitHub release asset, and upgrades the installed app.
