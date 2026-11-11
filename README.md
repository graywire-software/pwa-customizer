<img width="256" height="256" alt="icon_rounded" src="https://github.com/user-attachments/assets/1f2a6ed0-cfab-49e9-8579-6f845180c7b3" />


# PWA Customizer

PWA Customizer is a Chrome / Chromium extension for changing an installed web app's title-bar color and page title. Settings are saved per website.

## Install

1. Download or clone this repository.
2. Open `brave://extensions` in Brave or `chrome://extensions` in Chrome and enable **Developer mode**.
3. Select **Load unpacked** and choose the `extension` folder, which contains `manifest.json`.
4. Pin PWA Customizer from the extensions menu if you want quick access.

Keep the folder in place. After updating the files, reload the extension on the extensions page and reload any open app windows.

## Use

Open a website in a regular browser tab and select PWA Customizer. Enable either control and allow access when prompted. Your settings also apply to open app windows for that site; reload the window if a change does not appear.

- **Recolor title bar** offers light, dark, or a custom three- or six-digit hex color. It changes the browser's theme-color hint, not the website's own light or dark theme.
- **Change page title** offers a short title based on the site's app name or a custom title. Clear the custom title to use the website's title again. This also changes the title in regular browser tabs.

Settings are scoped to the site's origin (scheme, hostname, and port). Turning a control off restores the site's color or title while retaining your choice for later. Browser-protected pages cannot be customized.

The browser controls the final appearance of app windows. Colors may differ with browser or system settings, and the original color may appear briefly while an app starts. The extension cannot rename an installed app; the browser may include that name in the window title. If the detected short name differs from the installed app name, try entering the installed name as a custom title.

## Privacy and permissions

Preferences are stored locally in the browser profile. The extension requests access to each website when you enable a control. Disabling both controls stops automatic injection on that site; you can revoke the retained permission in the browser's extension settings.

The extension uses `activeTab` to identify the current site, `storage` to save settings, and `scripting` to apply them. Short title mode fetches the site's linked web app manifest, subject to the page's normal origin and CORS rules. There is no analytics or external name-detection service.

When the compatible [YouTools](https://github.com/graywire-software/youtools) extension is installed, YouTube color and title preferences are shared between the two extensions. Other sites' settings and page contents are not shared.

## Development

The extension runs directly from `extension/` without a build step. Python dependencies are needed for tests and icon generation:

```sh
python -m venv .venv
# Activate the virtual environment, then:
pip install -r requirements-dev.txt
python tests/observer_regression.py
python tests/browser_test.py
python scripts/make_icons.py
python scripts/package.py
```

The browser tests use an isolated profile and default to Brave's macOS path. Set `BROWSER_PATH` to your Chromium-based browser executable on other systems. Icon generation uses Playwright's Chromium by default; set `BROWSER_PATH` to use an existing browser, or install Playwright Chromium with `python -m playwright install chromium`. The packaging script creates `PWA-Customizer.zip` from the contents of `extension/`.

[YouTools](https://github.com/graywire-software/youtools) integration depends on the companion extension IDs configured in both projects. When publishing either extension under a different ID, update the IDs in both projects before packaging; the extensions still work independently without the companion.
