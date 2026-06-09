package storage

import (
	"os"
	"path/filepath"

	"github.com/ryangerardwilson/wb/internal/core"
)

type Store struct {
	Paths Paths
}

func New(paths Paths) Store {
	return Store{Paths: paths}
}

func (s Store) LoadConfig() (core.AppConfig, error) {
	if _, err := os.Stat(s.Paths.ConfigPath); err == nil {
		return readConfig(s.Paths.ConfigPath)
	} else if !os.IsNotExist(err) {
		return core.AppConfig{}, err
	}

	if s.Paths.LegacyConfigPath != "" {
		if _, err := os.Stat(s.Paths.LegacyConfigPath); err == nil {
			config, err := readConfig(s.Paths.LegacyConfigPath)
			if err != nil {
				return core.AppConfig{}, err
			}
			if err := s.SaveConfig(config); err != nil {
				return core.AppConfig{}, err
			}
			return config, nil
		} else if !os.IsNotExist(err) {
			return core.AppConfig{}, err
		}
	}

	return core.DefaultAppConfig(), nil
}

func (s Store) EnsureConfig() (string, error) {
	config, err := s.LoadConfig()
	if err != nil {
		return "", err
	}
	if _, err := os.Stat(s.Paths.ConfigPath); err == nil {
		return s.Paths.ConfigPath, nil
	} else if !os.IsNotExist(err) {
		return "", err
	}
	if err := s.SaveConfig(config); err != nil {
		return "", err
	}
	return s.Paths.ConfigPath, nil
}

func (s Store) SaveConfig(config core.AppConfig) error {
	if err := os.MkdirAll(filepath.Dir(s.Paths.ConfigPath), 0o755); err != nil {
		return err
	}
	return os.WriteFile(s.Paths.ConfigPath, core.FormatAppConfig(config), 0o644)
}

func readConfig(path string) (core.AppConfig, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return core.AppConfig{}, err
	}
	return core.ParseAppConfig(data)
}
