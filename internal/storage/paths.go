package storage

import (
	"errors"
	"os"
	"path/filepath"
)

const (
	AppName       = "writenow"
	LegacyAppName = "wb"
)

type Paths struct {
	ConfigPath       string
	LegacyConfigPath string
}

func DefaultPaths() (Paths, error) {
	configHome, err := configHome()
	if err != nil {
		return Paths{}, err
	}
	return Paths{
		ConfigPath:       filepath.Join(configHome, AppName, "config.json"),
		LegacyConfigPath: filepath.Join(configHome, LegacyAppName, "config.json"),
	}, nil
}

func configHome() (string, error) {
	if value := os.Getenv("XDG_CONFIG_HOME"); value != "" {
		return filepath.Clean(expandHome(value)), nil
	}
	home, err := os.UserHomeDir()
	if err != nil || home == "" {
		return "", errors.New("unable to determine home directory")
	}
	return filepath.Join(home, ".config"), nil
}

func expandHome(path string) string {
	if path == "~" {
		if home, err := os.UserHomeDir(); err == nil && home != "" {
			return home
		}
	}
	if len(path) > 2 && path[0] == '~' && os.IsPathSeparator(path[1]) {
		if home, err := os.UserHomeDir(); err == nil && home != "" {
			return filepath.Join(home, path[2:])
		}
	}
	return path
}
