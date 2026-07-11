# OKRA Phase A Deployment Templates

These files implement the Phase A3 Linux VM runtime described in
`docs/cloud_migration_plan.md`. They are examples, not production credentials
or an automatic cutover. The API remains bound to loopback; Cloudflare Tunnel
is the intended public ingress.

## Required Decisions

Before executing the templates, choose and configure:

- the real Cloudflare hostname and Access policy;
- a real Tunnel UUID and its root-owned credentials file;
- a long random API bearer token;
- whether browser/static serving through Caddy is needed;
- whether realtime polling should be enabled;
- a private R2 or OCI rclone remote for backups.

No example file contains a usable credential. Remote mutations are disabled in
the env example until Access and bearer-token checks have been verified.

## Layout

- `systemd/okra-api.service`: loopback Python API.
- `systemd/okra-daily.*`: weekday timer plus trading-calendar condition for the
  intraday daily pipeline.
- `systemd/okra-realtime.*`: ten-minute market-hours timer plus the same
  trading-calendar condition.
- `cloudflared/config.example.yml`: Tunnel to loopback Caddy on port 8080.
- `caddy/Caddyfile.example`: static React files plus `/api/*` reverse proxy.
- `env/okra.env.example`: placeholder-only runtime environment.
- `scripts/bootstrap_ubuntu.sh`: dry-run-first Ubuntu preparation.
- `scripts/healthcheck.sh`: local API, page, and dated-artifact validation.
- `scripts/backup_artifacts.sh`: allowlisted, checksummed private-state backup.
- `scripts/restore_artifacts.sh`: traversal-safe, checksum-verified restore into
  an empty non-active home.

All service templates assume `/opt/okra_assistant` and user/group `okra`, as in
the migration plan. Edit the templates consistently before installation if
those values change.

## Bootstrap

Run the dry run from a checked-out repository first:

```bash
sudo bash deploy/scripts/bootstrap_ubuntu.sh
```

Execute only after reviewing every printed action:

```bash
sudo bash deploy/scripts/bootstrap_ubuntu.sh --execute
```

Add `--with-node` only when the VM must build `frontend/dist`. The bootstrap
does not install vendor repositories for Caddy or cloudflared and does not
enable services. Install those two tools from their official repositories.

## Runtime Environment

The bootstrap copies the env example only when `/etc/okra/okra.env` is absent.
Replace every placeholder and preserve restrictive permissions:

```bash
sudoedit /etc/okra/okra.env
sudo chown root:okra /etc/okra/okra.env
sudo chmod 0640 /etc/okra/okra.env
```

Generate the bearer token locally on the VM, for example with
`openssl rand -hex 32`; do not paste it into this repository. Keep
`OKRA_DISABLE_REMOTE_MUTATIONS=1` through the initial read-only verification.

## Validate And Start systemd

Validate templates before enabling them:

```bash
sudo systemd-analyze verify /etc/systemd/system/okra-api.service
sudo systemd-analyze verify /etc/systemd/system/okra-daily.service
sudo systemd-analyze verify /etc/systemd/system/okra-realtime.service
systemd-analyze calendar 'Mon..Fri *-*-* 14:05:00 Asia/Shanghai'
systemd-analyze calendar 'Mon..Fri *-*-* 09..14:00/10:00 Asia/Shanghai'
```

Start the API and validate locally before enabling either timer:

```bash
sudo systemctl enable --now okra-api.service
sudo -u okra bash /opt/okra_assistant/deploy/scripts/healthcheck.sh --mode api
sudo systemctl enable --now okra-daily.timer
# Enable only after realtime data-source behavior is accepted on the VM:
sudo systemctl enable --now okra-realtime.timer
systemctl list-timers 'okra-*'
```

Daily and realtime services share `/run/lock/okra-pipeline.lock`, so they cannot
write concurrently. Exit code 75 means another OKRA pipeline owns the lock and
is treated as a non-failure. `ExecCondition` skips non-trading days according
to `config/trading_calendar.json` and the repository calendar helpers.

## Cloudflare And Caddy

Copy the examples outside the repository and replace every hostname/UUID:

```bash
sudo install -m 0600 deploy/cloudflared/config.example.yml /etc/cloudflared/config.yml
sudo install -m 0644 deploy/caddy/Caddyfile.example /etc/caddy/Caddyfile
sudo cloudflared tunnel ingress validate
sudo caddy validate --config /etc/caddy/Caddyfile
```

The Caddy example listens only on `127.0.0.1:8080`; the API listens only on
`127.0.0.1:8765`. Do not open either port in the VM firewall. If static browser
serving is not required, point the Tunnel directly to `127.0.0.1:8765` and do
not deploy the Caddy example.

systemd health checks inherit `/etc/okra/okra.env`. When `OKRA_API_TOKEN` is
configured, dated Today/Realtime page probes send it through a mode-0600
temporary curl header file; the token is never printed or placed in the curl
process arguments. The basic `/api/health` probe remains unauthenticated.

## Backup

The backup script defaults to dry-run and prints its allowlist:

```bash
sudo -u okra bash deploy/scripts/backup_artifacts.sh \
  --agent-home /opt/okra_assistant \
  --output-dir /var/backups/okra
```

Execution requires an explicit private-data acknowledgement. An rclone target
is optional and must already be configured as a private remote:

```bash
sudo -u okra bash deploy/scripts/backup_artifacts.sh \
  --agent-home /opt/okra_assistant \
  --output-dir /var/backups/okra \
  --rclone-destination 'private-r2:backups/okra' \
  --execute --confirm-private-data
```

Each archive contains `backup_metadata.env` and `manifest.sha256`; an external
`.sha256` file protects the archive itself. Cookie files, API-key-like files,
browser profiles, raw account screenshots, caches, and temporary files are
excluded. The archive still contains private holdings and execution state, so
bucket access controls and provider-side encryption remain mandatory.

## Restore Drill

Validate without writing the target:

```bash
bash deploy/scripts/restore_artifacts.sh \
  --archive /var/backups/okra/okra-YYYY-MM-DDTHHMMSSZ.tar.gz \
  --target-home /opt/okra_restore_test
```

Restore only into an absent or empty directory separate from the active home:

```bash
sudo bash deploy/scripts/restore_artifacts.sh \
  --archive /var/backups/okra/okra-YYYY-MM-DDTHHMMSSZ.tar.gz \
  --target-home /opt/okra_restore_test \
  --owner okra \
  --execute --confirm-restore
```

The restore validates the external archive checksum, archive member paths and
types, the internal per-file manifest, and secret-like filenames before any
target write. It never deletes or overwrites an existing target. Start a
separate API against the restored home and check health, Today, Portfolio, and
Execution before treating the drill as successful.
