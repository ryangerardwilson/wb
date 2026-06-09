package cli

import (
	"fmt"
	"io"
)

const helpText = `WriteNow
write long work one proposition at a time

global actions:
  writenow help
    show this help
  writenow version
    print the installed version
  writenow list
    list saved books with book numbers
  writenow start
    choose a saved book number and write the next proposition
  writenow start 1
    write the next proposition in book 1
  writenow tui
    select a saved book and browse drafts
  writenow upgrade
    upgrade to the latest release

features:
  create a generic book structure file
  # init [structure_json]
  writenow init
  writenow init ./structure.json

  save a book
  # preset save <name> structure <structure_json> drafts <drafts_dir>
  writenow preset save "an eye for an eye" structure ./structure.json drafts ./drafts

  start writing from the numbered book list
  # start [booknumber]
  writenow start
  writenow start 1

  browse saved books in the terminal UI
  # tui
  writenow tui

  open the next unfinished proposition in your editor
  # write <structure_json> drafts <drafts_dir> [first]
  writenow write ./structure.json drafts ./drafts
  writenow write ./structure.json drafts ./drafts first

  export completed draft bodies into a manuscript
  # export <structure_json> drafts <drafts_dir> [all] [to <output_md>]
  writenow export ./structure.json drafts ./drafts to manuscript.md
  writenow export ./structure.json drafts ./drafts all

  edit generic app defaults and machine-local presets
  # config
  writenow config
`

func WriteHelp(out io.Writer) {
	_, _ = fmt.Fprint(out, helpText)
}
