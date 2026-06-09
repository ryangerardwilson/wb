package l1

import "github.com/charmbracelet/lipgloss"

type Theme struct {
	Base       lipgloss.Style
	Title      lipgloss.Style
	Muted      lipgloss.Style
	Selected   lipgloss.Style
	Strong     lipgloss.Style
	Progress   lipgloss.Style
	Error      lipgloss.Style
	Background lipgloss.Color
}

func DefaultTheme() Theme {
	muted := lipgloss.Color("244")
	strong := lipgloss.Color("252")
	accent := lipgloss.Color("115")
	warn := lipgloss.Color("203")

	return Theme{
		Base: lipgloss.NewStyle().
			Foreground(strong).
			Padding(1, 2),
		Title: lipgloss.NewStyle().
			Foreground(strong).
			Bold(true),
		Muted: lipgloss.NewStyle().
			Foreground(muted),
		Selected: lipgloss.NewStyle().
			Foreground(strong).
			Bold(true),
		Strong: lipgloss.NewStyle().
			Foreground(strong).
			Bold(true),
		Progress: lipgloss.NewStyle().
			Foreground(accent),
		Error: lipgloss.NewStyle().
			Foreground(warn),
		Background: lipgloss.Color("235"),
	}
}
