# Robot icon instructions

## Scope

The included `assets/robot_icon.svg` is the untouched original. Only five accent color tokens are replaced: background gradient, eye/chest gradient and antenna tip. Geometry, body whites, shadows and outlines remain unchanged. Accent shades are derived by mixing the selected color with white or black.

Rendering needs Python 3.9+ and `rsvg-convert` on PATH. Rendering works on any operating system providing that executable. This package uses only the Python standard library. Installation is macOS-only and additionally needs `iconutil`, `codesign` and `ditto`; it does not install or modify Windows/Linux application icons.

## Import on another computer

Extract the `hermes-robot-icon` directory from the ZIP into the active instance's `$HERMES_HOME/skills/` (or the home-directory `.hermes/skills/` when unset). Do not overwrite an existing customized skill without reviewing it. On a non-Hermes agent, keep the directory anywhere and follow these instructions directly. The relative layout must remain intact. Open a new agent session if its skill catalog is cached.

The skill and original SVG live outside the application/repository, so app rebuilds do not overwrite them. An upgrade can overwrite the installed icon: run `--reapply` afterward. This is a manual restoration workflow, not an automatic update hook or a guarantee against future resource-layout changes. A different machine chooses its own accent and explicit app path; never copy `last.json` or backups between machines.

For example, use `--accent '#238B45'` for green or any exact six-digit RGB hex. Do not redraw or replace the supplied robot to change its accent. On macOS, `rsvg-convert` can be provided by Homebrew's `librsvg` package (`brew install librsvg`); verify the tool is present before running.

## Commands

Run these through the terminal tool from the skill directory. Set `APP_BUNDLE` yourself to the exact intended app bundle; never auto-discover an installation when multiple copies may exist.

```sh
python3 scripts/robot_icon.py --render-only --accent '#CB003D' --output preview
python3 scripts/robot_icon.py --apply --app "$APP_BUNDLE" --accent '#CB003D'
python3 scripts/robot_icon.py --reapply
python3 scripts/test_robot_icon.py -v
```

`--output` is a directory containing `robot.svg` and `robot.png`; existing files with those names are overwritten. Preview and inspect before applying. Quote the accent because an unquoted hash may begin a shell comment. Accepted format is exactly `#RRGGBB`.

First installation always requires both `--app` and `--accent`. Reapply deliberately uses the saved exact target, never searches for another installation, and fails if that target is missing. After an upgrade at a different path, use a fresh explicit apply instead.

## What installation does

1. Validate the target, tools, accent and free space. Reserve room for multiple full bundle copies. Backups accumulate and are not deleted automatically.
2. Save a timestamped full bundle backup under `$HERMES_HOME/custom-icon/backups`. If `HERMES_HOME` is unset, the home-directory `.hermes` folder is used. No state is stored in the skill.
3. Stage a complete bundle copy next to the target; preserve native metadata with `ditto`. All resource edits and signing happen in that copy first.
4. Render an ICNS icon and update the declared bundle icon. Patch `dist/apple-touch-icon.png` and/or `public/apple-touch-icon.png` in `app.asar`. Fail closed if neither exists.
5. Preserve every original archive entry and unpacked flag. Keep existing payload offsets; append replacement packed bytes and update only the replacement entries and SHA256 integrity records. This intentionally avoids repacking or adding a package-manager dependency. No asar package version needs pinning because none is used. Repeated applications add small unused old icon payloads; upgrades reset the archive.
6. Update the `Resources/app.asar` plist integrity hash, when present, from the raw JSON header bytes, not the whole archive. Other archive hashes remain unchanged and are verified.
7. Sign only the outer staged bundle ad hoc, preserving identifier, entitlements, requirements, flags and runtime metadata; nested signed components are not rewritten. Verify the complete signature and archive header hashes before swapping and again afterward.
8. Swap the verified staged bundle into place with sibling renames. Keep the old bundle until final verification succeeds; caught failures restore it. Save the successful target, accent and backup path in `$HERMES_HOME/custom-icon/last.json`.

## Safety and recovery

Ad-hoc signing replaces the original publisher signature and may invalidate trust, update assumptions or existing privacy permissions. You may have to grant permissions again. Do not use on a managed or protected installation without authorization. Unsupported resource layouts fail rather than guessing.

The script never quits the app, kills the Dock, restarts a process or removes quarantine attributes. A running app may keep showing the old icon. Restart it manually after success. Avoid concurrent upgrades or app writes during installation.

Ordinary exceptions and keyboard interruption trigger rollback. Power loss or an uncatchable process termination cannot be made transactional by this script: inspect `.robot-rollback-*` sibling copies and the backup before doing anything else. A leftover `apply.lock` in local state is intentional protection; remove it only after confirming no installer is running and recovery is complete.

For manual rollback, first quit the target yourself. Locate the full backup path reported by the script (or in local `last.json`). Preserve the current bundle separately, then copy the chosen backup back to the same target using `ditto`; verify with `codesign --verify --deep --strict "$APP_BUNDLE"`. Do not merge backup contents into a running or existing bundle. Retain the backup until the restored app starts successfully.

## macOS: Dock turns back to the old color after quitting

There are two icon sources: a running Electron app may set a runtime PNG, whereas the closed app's pinned Dock tile uses the bundle icon and system caches. A correct runtime icon alone is not proof of completion.

1. Read the intended bundle's `Info.plist` and `CFBundleIconFile`; decode that ICNS with `iconutil -c iconset` into a scratch directory and visually check it. If it is the old color, reapply to this bundle first. Verify the signature afterward.
2. Read `defaults export com.apple.dock -` as a plist and inspect the matching `persistent-apps` entry's `tile-data.file-data._CFURLString`. Compare it to the intended app and running executable. A different copy is not a cache issue. Do not reset the entire Dock or remove unrelated entries.
3. If the target and ICNS are correct, refresh registration and bundle modification time. Run the following through the terminal tool with the explicit `APP_BUNDLE` already selected:

```sh
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_BUNDLE"
touch "$APP_BUNDLE"
```

4. Tell the user that restarting the Dock makes it disappear briefly but does not quit their applications, then run `killall Dock` if within the authorized repair scope. The installer intentionally does not do this implicitly. Do not kill Hermes, Finder, or unrelated cache services.
5. Have the user quit and reopen the app when convenient, and check both closed and running states. Do not report visual success based only on file hashes. If still stale, remove and re-add only that app's pinned Dock tile, preserving its position where possible and backing up the Dock preferences before edits. Avoid deleting global icon caches.

## macOS: absent from Applications or Spotlight

A source build inside a hidden directory is not an Applications installation. Cache refresh alone does not create one. Check whether a real app bundle exists in `/Applications` or the user's `Applications` directory, and use `mdfind` with its bundle identifier to check discovery.

With user authorization, copy the verified bundle using `ditto` to the chosen Applications directory. Refuse to overwrite another installation without first inspecting and backing it up. Keep the source copy until the new one has launched successfully. Verify the destination signature, register it with `lsregister -f`, and run `mdimport` on the destination. Read back Spotlight results; indexing can lag or be excluded by system policy, so do not promise immediate search visibility.

If a pinned Dock tile still targets the source build, back up `defaults export com.apple.dock -` and update only its matching entry to the new app URL, preserving all other tiles. Remove that entry's old `book` bookmark when changing its URL, then read preferences back and restart the Dock. Never blindly replace all Dock preferences. Change local `custom-icon/last.json` to the destination or perform a fresh explicit apply there, so `--reapply` modifies the visible installed app rather than a hidden old copy.

Copying creates two bundles: future source builds update the source, not the installed Applications copy. Explicitly deploy the rebuilt bundle to the installed target before reapplying its icon, or use that installed app's normal updater. Keep this installation choice local, never in the exported skill. Do not automatically restart the app hosting the current agent session.

## Tests and export

Tests render a real PNG, compare the SVG's unchanged text outside accent tokens, reject invalid colors and missing targets, and on macOS sign/apply/verify a fake bundle with an archive and unpacked entry. An injected post-swap verification failure proves rollback restores the pre-apply archive and signature. Compare canonical resolved paths in failure injection so macOS symlink aliases do not silently bypass the rollback test. Tests never discover or modify an installed app.

Export only `SKILL.md`, `references/INSTRUCTIONS.md`, `assets/robot_icon.svg`, `scripts/robot_icon.py`, and `scripts/test_robot_icon.py`. Exclude previews, bytecode, local `last.json`, locks and backups. The original SVG retains its standards-required XML namespace identifier; it is not a network dependency or provenance label.
