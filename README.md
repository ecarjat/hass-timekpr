# Home Assistant Timekpr Integration

Custom Home Assistant integration to manage [`timekpr-next`](https://mjasnik.gitlab.io/timekpr-next/) on a remote Linux computer using the [`ssh` integration](https://github.com/zhbjsh/homeassistant-ssh).

## What this integration does

Per configured host, it can manage one or more `timekpr` users:
- Set daily limits (minutes per weekday)
- Set allowed windows (time-of-day intervals per weekday)
- Add bonus time
- Lock and unlock a user
- Expose remaining time/status as sensors

## Prerequisites

## 1) `timekpr-next` installed on the controlled computer

The remote computer must have `timekpra` available (default path is `/usr/bin/timekpra`).

## 2) SSH access from Home Assistant

This integration relies on the `ssh` integration and creates/links an SSH entry during config flow.

## 3) Passwordless sudo for `timekpra` (required)

The SSH user must be allowed to run `timekpra` without a password.

Example sudoers entry (edit with `visudo`):

```sudoers
# /etc/sudoers.d/timekpr-homeassistant
ha_ssh ALL=(root) NOPASSWD: /usr/bin/timekpra
Defaults:ha_ssh !requiretty
```

Replace `ha_ssh` with the SSH username used by Home Assistant.

Validate on the controlled computer:

```bash
sudo -n timekpra --help
```

The command must succeed without prompting for a password.

## Installation

1. Copy `custom_components/timekpr` into your Home Assistant config directory.
2. Restart Home Assistant.
3. Add integration: **Settings -> Devices & Services -> Add Integration -> Timekpr**.
4. Enter host, port, SSH username, private key, optional key passphrase.
5. Select managed users discovered from `timekpra --userlist`.

## Entities

For each managed user:
- `sensor`: Remaining Time (minutes left today)
- `switch`: Lockout
- `number` x7: Daily Limit `MON..SUN`
- `text` x7: Allowed Windows `MON..SUN` (`HH:MM-HH:MM[,HH:MM-HH:MM]`)
- `number`: Bonus Minutes
- `button`: Apply Bonus Time

## Services

- `timekpr.set_daily_limit`
  - `user`, `weekday` (`mon..sun`), `minutes`, optional `entry_id`
- `timekpr.set_allowed_windows`
  - `user`, `weekday`, `windows`, optional `entry_id`
- `timekpr.add_time`
  - `user`, `minutes`, optional `entry_id`
- `timekpr.lock_user`
  - `user`, optional `entry_id`
- `timekpr.unlock_user`
  - `user`, optional `entry_id`
- `timekpr.refresh_users`
  - optional `entry_id`

## Notes

- Lockout is implemented by exhausting remaining time for the day.
- Unlock restores previously cached remaining time for that user (or configured grace minutes if no cache exists).
- If multiple hosts manage the same username, include `entry_id` in service calls.

## Troubleshooting

- `sudo_password_required` during config flow:
  - Recheck sudoers and rerun `sudo -n timekpra --help` as the SSH user.
- `cannot_connect` during config or options:
  - Validate SSH key/host/port and that the linked `ssh` integration entry is online.
- No users found:
  - Confirm `sudo -n timekpra --userlist` returns expected users on the controlled computer.
