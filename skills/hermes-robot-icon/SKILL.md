---
name: hermes-robot-icon
description: Use when recoloring or installing a robot icon.
version: 0.2.0
platforms: [macos, linux, windows]
---

# Robot icon

Recolor the supplied robot without changing geometry or its pale body. Render portable SVG/PNG resources; explicitly apply to one macOS app bundle only.

## When to use
- Change the background, eyes, antenna tip and chest accent.
- Reapply the last local choice after an app upgrade.
- Do not use to redesign the robot or install icons on Windows/Linux.

## Procedure
Read `references/INSTRUCTIONS.md` before installing. Run `scripts/robot_icon.py` using Python 3 through the terminal tool. Preview first; never infer an installation path or quit an app automatically. Require an explicit target and accent for the first apply. Check the pinned Dock target separately from the running process. After installation, follow the macOS registration/cache procedure in the instructions; verification must distinguish the running runtime icon from the closed-app bundle icon. If the app lives in a hidden build directory, handle Applications/Spotlight installation explicitly rather than claiming cache refresh installs it.

## Pitfalls
Installation replaces the app's signature with an ad-hoc signature. Permissions may need granting again. Restart manually after success. Keep backups outside the app and never export local state.

## Verification
Run `python3 scripts/test_robot_icon.py -v` from this skill directory. Check the script's verified output and visually inspect the PNG. Export only this skill directory, excluding bytecode caches.
