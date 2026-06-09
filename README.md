# writenow

WriteNow is a terminal-native drafting tool for writing long work one proposition
at a time.

The app is generic. It does not ship with any book plan, manuscript, or private
writing material.

A proposition is complete when the draft body below the `writenow` marker
reaches the configured minimum character count. Legacy `wb` draft markers are
still read so existing drafts survive the rename.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/ryangerardwilson/wb/main/install.sh | bash
writenow version
```

The installer keeps the internal runtime under `~/.writenow/bin/writenow` and
publishes the user-facing command at `~/.local/bin/writenow`.

If `~/.local/bin` is not already on your `PATH`, add it once to `~/.bashrc` and
reload:

```sh
export PATH="$HOME/.local/bin:$PATH"
source ~/.bashrc
```

## Run From Source

```sh
go run ./cmd/writenow
go run ./cmd/writenow help
```

## Install From Source

```sh
./install.sh from .
writenow version
```

## Usage

```sh
writenow help
writenow version
writenow list
writenow start 1
writenow start
writenow tui
writenow upgrade
```

Create a generic book structure file:

```sh
writenow init
writenow init ./structure.json
```

Write the next proposition with explicit paths:

```sh
writenow write ./structure.json drafts ./drafts
writenow write ./structure.json drafts ./drafts first
```

Save a book and inspect progress from any directory:

```sh
writenow preset save "an eye for an eye" structure /path/to/structure.json drafts /path/to/drafts
writenow list
```

Start writing from the numbered book list:

```sh
writenow start 1
writenow start
```

Browse saved books in the TUI:

```sh
writenow tui
```

TUI keys:

```text
enter          select book
e              edit the current draft in vim
n/p            next or previous proposition
j/k or arrows  scroll
b              back to books
q              quit
```

Export completed draft bodies:

```sh
writenow export ./structure.json drafts ./drafts to manuscript.md
writenow export ./structure.json drafts ./drafts all
```

Edit the app config directly:

```sh
writenow config
```

## Config

App config is XDG compliant:

```text
$XDG_CONFIG_HOME/writenow/config.json
~/.config/writenow/config.json
```

On first read, `writenow` migrates an existing
`$XDG_CONFIG_HOME/wb/config.json` or `~/.config/wb/config.json` into the new
config path when the new file does not exist.

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

When `writenow` launches Vim or Neovim, it sets prose wrapping at `79`
characters with a `79` column marker. Draft files keep that as a plain comment
rather than a Vim option string.

## Release

This repo follows the workspace CLI contract:

```sh
./push_release_upgrade.sh
```

That script pushes the current branch, tags the next release, publishes the
GitHub release asset, and upgrades the installed app. Release artifacts are
Linux x64 tarballs named `writenow-linux-x64.tar.gz`.
