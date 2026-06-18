## Changelog

All notable changes to this project will be recorded in this file.

The format is based on Keep a Changelog, with a pragmatic structure tailored for this repository.

## [Unreleased]

## [1.2.7] - 2026-06-18

### Fixed
- Backup progress rendering now uses integer `expand` values to avoid Flet frame update failures during transfer progress refresh.

## [1.2.6] - 2026-06-18

### Added
- In-app update now supports one-click restart installation for packaged desktop builds on macOS and Windows.

### Changed
- Theme switching now rebuilds the current task stage without dropping compare, confirm, backup, or result state.
- History rows now show source and target path flow together with status for quicker scanning.
- Main window default size is increased to provide a more stable desktop layout.

### Fixed
- Restart-based self update now closes the old window more reliably before relaunching the new build.

## [1.2.5] - 2026-06-17

### Added
- Light / dark theme switching with persisted theme preference.
- SVG icon set for comparison summary statistics.

### Changed
- Settings page grouped into cleaner cards.
- History status presentation refined for quicker scanning.
- Release governance upgraded to clearer categories and labels.
- Repository governance: release notes, issue templates, PR template, and label taxonomy.

### Fixed
- Update download asset resolution is more robust against naming differences.
- Settings switches now correctly respect the disabled state for unsupported options such as system autostart.

## [1.2.4] - 2026-06-15

### Added
- System autostart option in Settings.

### Changed
- Settings UI grouping and visual hierarchy.

## [1.2.3] - 2026-06-12

### Fixed
- Windows native directory picker now enables DPI awareness to reduce blurry rendering on scaled displays.

## [1.2.2] - 2026-06-12

### Added
- In-app update download with inline progress and reveal-in-folder action.

## [1.2.1] - 2026-06-11

### Changed
- Native directory picker unified across macOS and Windows with subprocess isolation.

## [1.2.0] - 2026-06-11

### Changed
- Promoted the desktop line to `v1.2.0`.
