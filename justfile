# Bookmarkwise: all commands run from the repo root. Working files go to ./work (git-ignored).

chromium := env_var_or_default("CHROMIUM", "")

# Read-only first look at your Chrome bookmarks: profiles, then the inventory of PROFILE
run PROFILE="Default":
    mkdir -p work
    python3 -m bookmarkwise profiles
    python3 -m bookmarkwise inventory --profile "{{PROFILE}}" --out work/inventory.json

# Link the skill into ~/.claude/skills (manual install without the plugin system)
install:
    mkdir -p ~/.claude/skills
    ln -sfn "$(pwd)/skills/bookmarkwise" ~/.claude/skills/bookmarkwise
    @echo "Installed: ~/.claude/skills/bookmarkwise -> $(pwd)/skills/bookmarkwise"

test:
    python3 -m pytest -q

# Real browser, throwaway profile: CHROMIUM=/path/to/chromium just e2e
e2e:
    CHROMIUM="{{chromium}}" node tests/e2e/run.mjs

# The demo profile, start to finish without a browser -> examples/walkthrough.txt
demo:
    bash examples/walkthrough.sh

# Re-render docs/bookmarkwise.gif from docs/animation/sketch.js (needs ffmpeg)
gif:
    CHROMIUM="{{chromium}}" node docs/animation/render.mjs
