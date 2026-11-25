# samik-bot

[![CI](https://github.com/i-got-this-faa/samik-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/i-got-this-faa/samik-bot/actions/workflows/ci.yml)
[![Powered by OrcaRouter](https://img.shields.io/badge/Powered_by-OrcaRouter-2563eb)](https://www.orcarouter.ai/ref/ref_b7dd35655fa712a6b8b0)

samik-bot is a self-hosted GitHub pull request review bot. Comment `@samik-bot review please` on a PR to request a review. The bot posts a summary with a Mermaid sequence diagram, then adds inline findings anchored to changed lines. The web dashboard shows progress, results, and any failure details.

Reviews run on demand in a Linux Bubblewrap sandbox with a read-only PR checkout. The default reviewer is [OpenCode V2](https://opencode.ai/v2/docs) with the `orcarouter/auto` model. The service also supports [pi](https://github.com/earendil-works/pi) and OpenCode Zen.

## Request a review

1. Sign in to the bot's dashboard with GitHub once, including if you are an administrator.
2. On an allowlisted PR, add a new conversation comment with `@samik-bot review please`. Use your deployment's configured bot mention if it differs.
3. Look for the 👀 reaction when the worker starts and follow progress at `/dashboard`. A completed review posts the summary, any findings that map to the diff, and a 🚀 reaction on the request.

The operator grants review access by numeric GitHub user ID. The PR's installation and repository must both be on the deployment's allowlists. Each PR can have one active review at a time.

## Set up an instance

### 1. Install the development dependencies and runtime

Install [Mise](https://mise.jdx.dev/) and use the Go and Bun versions pinned in [mise.toml](mise.toml).

```bash
git clone https://github.com/i-got-this-faa/samik-bot.git
cd samik-bot
make setup
cp .env.example .env
```

For a running instance, use a Linux host with Bubblewrap and stage the selected reviewer separately. For the default OpenCode reviewer, install a pinned stable V2 release and place the executable and its dependencies under a trusted runtime directory such as `/opt/opencode-runtime`. Set `OPENCODE_RUNTIME_DIR` to that directory and `BUBBLEWRAP_BIN` to the trusted Bubblewrap executable's direct path.

```bash
OPENCODE_BIN=/opt/opencode-runtime/bin/opencode mise exec -- make opencode-check
```

This checks the CLI's version and help commands. Service startup separately validates the runtime and starts the CLI inside Bubblewrap. Use a runtime tree owned by root or the service user, with no symlinks or group- or world-writable entries. See the [operations guide](docs/operations.md) for deployment requirements.

### 2. Register the GitHub App and OAuth App

Open **GitHub Settings → Developer settings** and create these two registrations.

| Registration | What to configure |
| --- | --- |
| **GitHub App** | Set the homepage to `PUBLIC_URL`, set the webhook URL to `https://<host>/webhooks/github`, and use a generated webhook secret. Subscribe to **Issue comment**. Grant **Contents: Read-only**, **Pull requests: Read and write**, and **Issues: Read and write**. |
| **GitHub OAuth App** | Set the homepage to `PUBLIC_URL` and the authorization callback URL to `<PUBLIC_URL>/auth/github/callback`. Copy the client ID and generate a client secret for dashboard sign-in. |

From the GitHub App settings, copy the **App ID** and generate a private key. Install the App on the test repository and record the installation and repository numeric IDs. You can find both in a webhook delivery as `installation.id` and `repository.id`.

Set `BOT_GITHUB_ID` to the numeric user ID of the installed App's bot account. With the GitHub CLI, replace `YOUR-APP-SLUG` with the slug from the App's settings URL.

```bash
gh api 'users/YOUR-APP-SLUG%5Bbot%5D' --jq '.id'
```

You can also read `user.id` from an existing comment by that account through the GitHub REST API. The bot uses this ID to recognize its own comments during publication recovery.

### 3. Configure and start the service

Fill in [.env.example](.env.example)'s settings in your local `.env`. Generate separate values for `GITHUB_WEBHOOK_SECRET` and `SESSION_SECRET` with `openssl rand -hex 32`. Keep the session secret with the database because it is used to derive the encryption key for the stored gateway credentials.

```bash
mise exec -- make run-local
curl -fsS http://localhost:8080/healthz
```

Run the health check from a second terminal while the service is running. A `{"status":"ok"}` response confirms that the review worker is ready and SQLite responds. Use your configured port if it differs from `8080`. For a live webhook test, point GitHub at a reachable HTTPS endpoint for the service and set `PUBLIC_URL` to that origin.

### 4. Connect a gateway key and test

1. Sign in at `PUBLIC_URL` as a user listed in `ADMIN_GITHUB_IDS`.
2. Add an authorized gateway key at `/admin/keys`, or use **Connect with OrcaRouter** at `/admin/partner` to add an OrcaRouter key through the provider's consent flow. The server stores pooled keys encrypted in SQLite.
3. Check the active model at `/admin/settings`. Use OrcaRouter keys for `orcarouter/…` models and OpenCode Zen keys for `opencode/…` models. The pool selects the least-used eligible key across the entire pool, so use keys from a single gateway and switch the pool and model together.
4. Request a review on a test PR and watch the status move from `queued` to `running` to `done`. Live reviews can incur gateway charges.

## Configuration

[.env.example](.env.example) contains the complete list and local defaults. The service reads process environment variables. `make run-local` sources `.env` for development, and production deployments inject environment variables directly.

| Setting | Value |
| --- | --- |
| `GITHUB_APP_ID`, `GITHUB_WEBHOOK_SECRET` | Required GitHub App ID and matching webhook secret. |
| `GITHUB_APP_PRIVATE_KEY_PATH` or `GITHUB_APP_PRIVATE_KEY` | Required private key as a file path or inline PEM. The file path takes precedence. |
| `BOT_GITHUB_ID` | Required numeric user ID of the App's bot account. |
| `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET` | Required for dashboard login and initial requester registration. |
| `ADMIN_GITHUB_IDS`, `REVIEWER_GITHUB_IDS` | Required admin list and optional review-only list. Both accept comma-separated positive numeric GitHub user IDs. |
| `ALLOWED_GITHUB_INSTALLATION_IDS`, `ALLOWED_GITHUB_REPOSITORY_IDS` | Required comma-separated numeric target IDs. Both lists must match the PR target. |
| `BOT_USERNAME` | Mentionable login without `@`. Defaults to `samik-bot`. |
| `SESSION_SECRET` | Required, at least 32 bytes. Retain it across restarts and restores. |
| `ZEN_DEFAULT_MODEL` | Required initial `provider/model` value. The example sets `orcarouter/auto`. Admins can override it at `/admin/settings`. |
| `REVIEW_ENGINE` | Defaults to `opencode`. Also accepts `pi` and the compatibility value `opencode2`. |
| `OPENCODE_RUNTIME_DIR`, `OPENCODE_BIN` | Runtime directory required for OpenCode. The default executable resolves to `$OPENCODE_RUNTIME_DIR/bin/opencode`. |
| `PI_RUNTIME_DIR`, `PI_BIN` | Runtime directory required for pi. The default executable resolves to `$PI_RUNTIME_DIR/bin/pi`. |
| `BUBBLEWRAP_BIN` | Required for both engines. Set a direct path such as `/usr/bin/bwrap`. |
| `PORT`, `PUBLIC_URL`, `DB_PATH` | Defaults to `8080`, `http://localhost:$PORT`, and `samik-bot.db`. Use HTTPS and durable storage in production. |
| `COOKIE_SECURE` | Defaults to true for an HTTPS `PUBLIC_URL`. HTTPS deployments require secure cookies. |
| `REVIEW_CONCURRENCY`, `REVIEW_TIMEOUT_MINUTES`, `ZEN_COOLDOWN_MINUTES` | Defaults to 2 workers, a 20-minute review timeout, and a 60-minute key cooldown. |
| `USER_REVIEWS_PER_HOUR`, `REPO_REVIEWS_PER_HOUR`, `MAX_ACTIVE_REVIEWS` | Defaults to 6 reviews per user per hour, 30 per repo per hour, and 50 active reviews. |
| `ORCAROUTER_REFERRAL_CODE` | Optional override for the referral code used by the partner dashboard and Connect flow. |
| `LOG_LEVEL` | Defaults to `info`. Also accepts `debug`, `warn`, and `error`. |

Use immutable numeric GitHub IDs throughout. Startup rejects duplicate IDs within a list and a non-empty legacy `ADMIN_GITHUB_LOGINS` setting. Configure at least one administrator before starting the service.

### Run reviews with pi

Set `REVIEW_ENGINE=pi` and `PI_RUNTIME_DIR`. Stage the pi launcher, Node executable, package, and dependencies in the trusted runtime tree. Preserve the package layout, including `package.json` above `dist/`. Give the launcher an absolute shebang pointing to an interpreter inside the staged tree. For a shell launcher, bundle the shell and invoke the bundled Node executable with the installed pi CLI entry point.

```bash
PI_BIN=/opt/pi-runtime/bin/pi mise exec -- make pi-check
```

Startup runs a gateway-specific model catalog probe inside Bubblewrap. pi supports OrcaRouter and paid OpenCode Zen models. OpenCode Zen free models require the OpenCode reviewer.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Sign-in fails | Confirm both OAuth credentials are set and that the callback matches `PUBLIC_URL` exactly. |
| The comment produces no review | In GitHub App **Recent deliveries**, check the `issue_comment` delivery response. Verify the webhook secret, mention, target allowlists, requester registration, and requester access. A PR with an active review or a request over the configured capacity limits will skip admission. |
| Startup reports a sandbox preflight error | Check the configured binary path, runtime directory ownership and permissions, and Bubblewrap support on the Linux host. |
| The review shows `failed` | Open the review detail and check the reported cause alongside the service log. For gateway failures, check the model, eligible keys, and provider limits. For agent or sandbox failures, use the sanitized stderr excerpt in the log. |
| The review shows `reconciliation_required` | GitHub may have accepted a comment before delivery could be confirmed locally. The worker checks for the original comment and keeps the PR's review slot occupied. Follow the [publication reconciliation runbook](docs/operations.md#publication-reconciliation-runbook). |

Deploy a single service replica with persistent SQLite storage. See [deployment and operations](docs/operations.md) for HTTPS, backups, rollout checks, and key-pool governance.

## Develop and build

```bash
mise exec -- make check
mise exec -- make build
```

`make check` verifies Go formatting, runs `go vet` and Go tests, builds the dashboard, and builds the binary. `make build` embeds the React dashboard in `bin/samik-bot`. For frontend development, run `mise exec -- make web-dev` in a second terminal while the Go service runs locally. Vite listens on port `5173` and proxies the API, OAuth, health, and webhook routes to port `8080`.

| Location | Responsibility |
| --- | --- |
| [cmd/samik-bot](cmd/samik-bot) | Service wiring and startup |
| [internal/server](internal/server) and [internal/gh](internal/gh) | GitHub webhooks and REST, OAuth, dashboard API, and OrcaRouter Connect |
| [internal/bot](internal/bot), [internal/runner](internal/runner), and [internal/review](internal/review) | Review queue workers, sandboxed execution, findings parsing, and publication |
| [internal/store](internal/store) and [internal/pool](internal/pool) | SQLite persistence, encrypted credentials, and key selection |
| [web](web) | React dashboard and embedded frontend assets |

The dashboard uses the `samik_session` cookie. Its JSON API provides `GET /api/me`, `GET /api/reviews` (up to 50 visible reviews), and `GET /api/reviews/{id}` (`review`, `findings`, and `events`). Administrators manage masked keys at `/api/admin/keys`, the active model at `/api/admin/settings`, and partner information at `/api/admin/partner`.
