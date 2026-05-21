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
wb -h
wb -v
wb -u
```

Create a generic book structure file:

```bash
wb init
wb init ./structure.json
```

Write the next proposition with explicit paths:

```bash
wb ./structure.json ./drafts
wb ./structure.json ./drafts -1
```

Inspect progress:

```bash
wb ./structure.json ./drafts status
wb ./structure.json ./drafts ls
wb ./structure.json ./drafts show
```

Export completed draft bodies:

```bash
wb ./structure.json ./drafts export -o manuscript.md
wb ./structure.json ./drafts export -all
```

Save a named preset and use it from any directory:

```bash
wb preset "an eye for an eye" /path/to/structure.json /path/to/drafts
wb "an eye for an eye"
wb "an eye for an eye" status
wb "an eye for an eye" export -o manuscript.md
```

Edit the app config directly:

```bash
wb conf
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
