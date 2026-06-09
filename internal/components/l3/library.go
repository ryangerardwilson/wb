package l3

import (
	"fmt"
	"strings"

	"github.com/ryangerardwilson/wb/internal/components/l1"
	"github.com/ryangerardwilson/wb/internal/components/l2"
	"github.com/ryangerardwilson/wb/internal/core"
)

type PickerView struct {
	Projects []core.TUIProject
	Selected int
	Height   int
}

type ReaderView struct {
	Project core.TUIProject
	Index   int
	Scroll  int
	Width   int
	Height  int
	Message string
	Error   string
}

func RenderPicker(theme l1.Theme, view PickerView) string {
	if len(view.Projects) == 0 {
		return theme.Base.Render(strings.Join([]string{
			theme.Title.Render("writenow"),
			"",
			theme.Muted.Render("No projects saved."),
			theme.Muted.Render("Run writenow preset save <name> structure <structure_json> drafts <drafts_dir>"),
		}, "\n"))
	}

	bodyHeight := max(view.Height-4, 1)
	offset := min(max(0, view.Selected-bodyHeight/2), max(len(view.Projects)-bodyHeight, 0))
	rows := []string{
		theme.Title.Render("writenow books"),
		l2.RenderProjectHelp(theme),
		"",
	}
	for index := offset; index < min(offset+bodyHeight, len(view.Projects)); index++ {
		rows = append(rows, l2.RenderRow(theme, index == view.Selected, core.ProjectRow(view.Projects[index])))
	}
	rows = append(rows, "", theme.Muted.Render(fmt.Sprintf("%d project(s)", len(view.Projects))))
	return theme.Base.Render(l2.JoinRows(rows))
}

func RenderReader(theme l1.Theme, view ReaderView) string {
	header, err := core.ItemHeader(view.Project, view.Index)
	if err != nil {
		header = err.Error()
	}
	lines, err := core.ItemLines(view.Project, view.Index, max(view.Width-4, 20))
	if err != nil {
		lines = []string{err.Error()}
	}
	contentHeight := max(view.Height-4, 1)
	maxScroll := max(len(lines)-contentHeight, 0)
	scroll := min(view.Scroll, maxScroll)

	rows := []string{
		theme.Title.Render(header),
		l2.RenderReaderHelp(theme),
		"",
	}
	rows = append(rows, lines[scroll:min(scroll+contentHeight, len(lines))]...)
	rows = append(rows, "", theme.Muted.Render(fmt.Sprintf("scroll %d/%d", scroll, maxScroll)))
	if view.Message != "" {
		rows = append(rows, theme.Muted.Render(view.Message))
	}
	if view.Error != "" {
		rows = append(rows, theme.Error.Render(view.Error))
	}
	return theme.Base.Render(l2.JoinRows(rows))
}
