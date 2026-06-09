# Product Engineer Role

## Purpose

Own writenow-specific facts that should not live in root generalists.

## Load Guidance

Load this file for `writenow` implementation, CLI/TUI, installer, release,
storage, configuration, or project-specific product work.

Root generalists own role behavior. This file owns only project facts and
repo-local operating constraints.

## Owns

- repo-local product and implementation facts
- CLI/TUI contract, command grammar, config, storage, and installer constraints
- release, upgrade, and verification expectations specific to this app

## Project Context

## Scope

- `writenow` is a generic writing CLI/TUI for drafting long work one proposition at a time.
- Keep the app independent of any specific book, manuscript, author plan, or private project.
- Do not commit book outlines, manuscript drafts, proposition lists, or generated drafts to this repo.
- Book-specific data belongs in the user's book project as a separate JSON structure file and draft files.

## Config

- App config is XDG compliant: `$XDG_CONFIG_HOME/writenow/config.json`, falling back to `~/.config/writenow/config.json`.
- On first read, the Go app may migrate legacy `$XDG_CONFIG_HOME/wb/config.json` or `~/.config/wb/config.json` into the new path when the new config does not exist.
- `writenow config` opens the app config.
- The app config may contain generic defaults and machine-local presets only:
  - `extension`
  - `min_chars`
  - `presets`
- A preset maps a user-facing name to a structure JSON path and drafts directory.
- Do not put book-specific planning content in the app repo or app config.

## Command Shape

- Keep the primary target explicit and declarative:
  - `writenow init [structure_json]`
  - `writenow write <structure_json> drafts <drafts_dir> [first]`
  - `writenow export <structure_json> drafts <drafts_dir> [all] [to <output_md>]`
  - `writenow list`
  - `writenow start [booknumber]`
  - `writenow tui`
  - `writenow config`
- Preserve saved books through the declarative preset surface:
  - `writenow preset save "an eye for an eye" structure <structure_json> drafts <drafts_dir>`
  - `writenow list`
  - `writenow start 1`
  - `writenow start`
- `writenow list` is the numbered saved-book surface. The number shown there
  is the `booknumber` accepted by `writenow start <booknumber>`.
- Bare `writenow start` prompts for a book number.
- In `writenow tui`, reader-mode key `e` opens the currently selected draft in
  Vim, scaffolding the draft first when it does not exist, then refreshes
  progress after Vim exits.
- Do not reintroduce the old direct path, bare preset, `conf`, `ls`, `-1`,
  `-all`, `-o`, or named `use <preset>` command forms.
- No-arg `writenow` prints help through the app-local CLI contract.

## Go Rewrite

- The app is implemented in Go with the same structural direction as
  `/home/ryan/Apps/boxes`: `cmd/writenow`, `internal/cli`, `internal/core`,
  `internal/storage`, `internal/app`, and `internal/components/l1-l3`.
- The installer publishes `~/.local/bin/writenow` and keeps the runtime binary
  under `~/.writenow/bin/writenow`.
- Release artifacts are Linux x64 tarballs named `writenow-linux-x64.tar.gz`.
- New draft scaffolds use `<!-- writenow:draft:start -->`; legacy
  `<!-- wb:draft:start -->` files remain readable and are normalized when
  opened through `writenow write`.
