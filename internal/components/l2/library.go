package l2

import (
	"fmt"
	"strings"

	"github.com/ryangerardwilson/wb/internal/components/l1"
)

func RenderProgress(theme l1.Theme, done int, total int) string {
	if total == 0 {
		return theme.Muted.Render("no propositions")
	}
	percent := 0
	if total > 0 {
		percent = int(float64(done)/float64(total)*100 + 0.5)
	}
	return theme.Progress.Render(fmt.Sprintf("%d/%d (%d%%)", done, total, percent))
}

func RenderProjectHelp(theme l1.Theme) string {
	return theme.Muted.Render("enter select  j/k move  q quit")
}

func RenderReaderHelp(theme l1.Theme) string {
	return theme.Muted.Render("e edit  n next  p previous  j/k scroll  b books  q quit")
}

func RenderRow(theme l1.Theme, selected bool, text string) string {
	cursor := " "
	if selected {
		cursor = ">"
	}
	line := fmt.Sprintf("%s %s", cursor, text)
	if selected {
		return theme.Selected.Render(line)
	}
	return line
}

func JoinRows(rows []string) string {
	return strings.Join(rows, "\n")
}
