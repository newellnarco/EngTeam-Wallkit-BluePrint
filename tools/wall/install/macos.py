"""macOS adapter — LaunchAgent. STUB."""

MANUAL = """
# ~/Library/LaunchAgents/com.max3.wall.courier.plist
#   ProgramArguments: python3 ~/.wall/sweep_all.py
#   StartInterval:    120
#   RunAtLoad:        true

launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.max3.wall.courier.plist
launchctl print gui/$(id -u)/com.max3.wall.courier
launchctl bootout  gui/$(id -u)/com.max3.wall.courier
"""


def install(interval_seconds: int = 120) -> str:
    raise NotImplementedError(f"macOS adapter is a stub:\n{MANUAL}")


def verify() -> dict:
    raise NotImplementedError("Not built. Check: launchctl print gui/$(id -u)/com.max3.wall.courier")


def uninstall() -> None:
    raise NotImplementedError("Not built. Run: launchctl bootout gui/$(id -u)/com.max3.wall.courier")
