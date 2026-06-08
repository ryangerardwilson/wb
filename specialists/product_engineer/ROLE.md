# Product Engineer Role

## Purpose

Own wb-specific facts that should not live in root generalists.

## Load Guidance

Load this file for `wb` implementation, CLI/TUI, installer, release, storage, configuration, or project-specific product work.

Root generalists own role behavior. This file owns only project facts and
repo-local operating constraints.

## Owns

- repo-local product and implementation facts
- CLI/TUI contract, command grammar, config, storage, and installer constraints
- release, upgrade, and verification expectations specific to this app

## Project Context

## Scope

- `wb` is a generic writing CLI for drafting long work one proposition at a time.
- Keep the app independent of any specific book, manuscript, author plan, or private project.
- Do not commit book outlines, manuscript drafts, proposition lists, or generated drafts to this repo.
- Book-specific data belongs in the user's book project as a separate JSON structure file and draft files.

## Config

- App config is XDG compliant: `$XDG_CONFIG_HOME/wb/config.json`, falling back to `~/.config/wb/config.json`.
- `wb config` opens the app config.
- The app config may contain generic defaults and machine-local presets only:
  - `extension`
  - `min_chars`
  - `presets`
- A preset maps a user-facing name to a structure JSON path and drafts directory.
- Do not put book-specific planning content in the app repo or app config.

## Command Shape

- Keep the primary target explicit and declarative:
  - `wb init [structure_json]`
  - `wb write <structure_json> drafts <drafts_dir> [first]`
  - `wb export <structure_json> drafts <drafts_dir> [all] [to <output_md>]`
  - `wb list`
  - `wb tui`
  - `wb config`
- Preserve named presets through the declarative preset surface:
  - `wb preset save "an eye for an eye" structure <structure_json> drafts <drafts_dir>`
  - `wb use "an eye for an eye"`
  - `wb use "an eye for an eye" status`
  - `wb use "an eye for an eye" list`
  - `wb use "an eye for an eye" show`
  - `wb use "an eye for an eye" export [all] [to <output_md>]`
- Do not reintroduce the old direct path, bare preset, `conf`, `ls`, `-1`,
  `-all`, or `-o` command forms.
- No-arg `wb` prints help through the app-local CLI contract.
