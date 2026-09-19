"""Linux adapter — systemd user timer, cron fallback. STUB."""

MANUAL = """
# ~/.config/systemd/user/wall-courier.service
#   [Service] Type=oneshot
#   ExecStart=/usr/bin/python3 %h/.wall/sweep_all.py
#
# ~/.config/systemd/user/wall-courier.timer
#   [Timer] OnBootSec=1min
#           OnUnitActiveSec=2min
#   [Install] WantedBy=timers.target

systemctl --user daemon-reload
systemctl --user enable --now wall-courier.timer
systemctl --user list-timers wall-courier.timer
systemctl --user disable --now wall-courier.timer

# Where user systemd is unavailable:
#   */2 * * * * /usr/bin/python3 $HOME/.wall/sweep_all.py
"""


def install(interval_seconds: int = 120) -> str:
    raise NotImplementedError(f"Linux adapter is a stub:\n{MANUAL}")


def verify() -> dict:
    raise NotImplementedError("Not built. Check: systemctl --user list-timers wall-courier.timer")


def uninstall() -> None:
    raise NotImplementedError("Not built. Run: systemctl --user disable --now wall-courier.timer")
