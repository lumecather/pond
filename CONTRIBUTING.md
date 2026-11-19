# Contributing to Pond

Thanks for wanting to help! This guide explains how the code is organised, how to run it, and how to send a change.

Pond is a Django app that runs inside a desktop window. If you know Django, you already know most of it.

## Ways to help

- **Report a bug** or **suggest an idea** in [Issues](../../issues). Screenshots and the log file help a lot (`pond.log` in the data folder, see below).
- **Improve a guide.** Guides are Markdown in `guides/starter.py`; fixing an explanation is a great first pull request.
- **Add a token or a network** (see "Common tasks").
- **Pick something from the roadmap** in the README. Please open an issue first for anything big, so we can agree on the approach before you spend time on it.

Security problems: please report them privately, see [SECURITY.md](SECURITY.md).

## Setup

You need Python 3.11+ and git.

```bash
git clone https://github.com/<you>/pond.git    # your fork
cd pond
python -m venv .venv
.venv\Scripts\activate                         # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python desktop.py --browser                    # run the app in your browser, handy while developing
python manage.py test                          # run the tests
```

`desktop.py` keeps its data in the user data folder (`%APPDATA%\Pond`, `~/Library/Application Support/Pond`, `~/.local/share/pond`). To keep a separate dev database, set `POND_DATA`:

```bash
set POND_DATA=C:\tmp\pond-dev                  # macOS/Linux: export POND_DATA=/tmp/pond-dev
```

`POND_DEBUG=1` turns on Django's debug pages.

## How it works

```
desktop.py ──► Django on 127.0.0.1:<random port>  (waitress)
          ├──► bot thread: every 15 s → engine.check_rules()
          └──► pywebview window opens /desktop/start/?token=<per-launch token>
```

- **Access.** `bot/desktop.py` (middleware) lets in only a session that came through the launch token, then sends you to `/setup/` (choose a password) or `/unlock/` until the vault is unlocked. There is one local user.
- **Password vault.** `bot/services/vault.py` derives a Fernet key from the password with scrypt. Only a salt and an encrypted check string are stored (`AppSetting`); the key lives in memory. `bot/services/crypto.py` encrypts the trading wallet's private key with it.
- **Settings.** RPC URLs, the buy limit and the withdrawal address are `AppSetting` rows (`bot/services/config.py`). An environment variable named like the network's `rpc_env` (e.g. `WEB3_PROVIDER_ETHEREUM`) also works as a fallback.
- **Prices.** `bot/services/prices.py` quotes a 0.05 ETH test buy over every Uniswap V2 and V3 pool (`dex.quotes`) and takes the best route, the same one a live trade would use. A test trade instead of "1 token" means a near-empty pool with a stale or manipulated price can't win. The pool fee is taken back out of the quote, so the result is the mid price: the same number the chart shows, and demo trades charge their 0.3 % fee once, like a real swap. If no pool answers it falls back to GeckoTerminal. Results are cached for 10 s.
- **Chart data.** `bot/services/market.py`: candles, volume, liquidity and trending pools from the GeckoTerminal public API. Everything is cached because the API allows about 30 requests a minute.
- **Trading.** `bot/services/trading.py` is the single entry point (`execute_order`). Demo trades are simulated in the database (`PaperBalance`). Live trades go to `bot/services/live.py`: pick the best route over Uniswap V2 and three V3 fee tiers (`dex.py`), approve the exact amount when selling, simulate with `estimate_gas`, sign, send (through Flashbots Protect if the network has a private RPC), wait for the receipt.
- **Rules.** `bot/services/engine.py` checks enabled rules against the USD price and calls `execute_order`. A rule without "repeat" switches off after it fires; a repeating one fires at most once an hour. A failed attempt doesn't switch a rule off: it retries every 5 minutes and gives up after 3 failures in a row. Live rules wait while the app is locked. Each rule runs in its own `try`, so one broken rule can't stop the others.
- **Guides.** `guides/starter.py` holds the texts; a migration loads them. `[[fig:name]]` in a guide inserts an SVG drawn by `guides/figures.py`.

### Project layout

| Path | What's inside |
|---|---|
| `desktop.py` | launcher: server, bot thread, window, single-instance lock |
| `config/` | Django settings; `paths.py` picks the data folder |
| `bot/models.py` | `Network`, `Token`, `TradingWallet`, `Rule`, `Order`, `PaperBalance`, `AppSetting` |
| `bot/services/` | everything that isn't a view: prices, market data, trading, live mode, DEX calls, rules, vault |
| `bot/views.py` | Pond, Trade, Market, Rules, Wallet, History; JSON for the chart and live price |
| `bot/views_desktop.py` | launch login, password screens, Settings |
| `bot/tests/` | tests (see below) |
| `bot/testdata/` | `Mocks.sol`: fake Uniswap contracts for live-mode tests, compiled into `mocks.json` |
| `guides/` | guide model, texts and illustrations |
| `templates/`, `static/` | HTML templates, one CSS file, small vanilla JS files; no build step |
| `pond.spec`, `build_exe.bat` | PyInstaller build of `Pond.exe` |

## Tests

```bash
python manage.py test                          # everything
python manage.py test bot.tests.test_live      # just live mode
```

- `bot/tests/base.py` has `AppTestCase`: a local user with a password set and a logged-in client. Use it for anything that renders a page.
- Network calls are never made in tests: patch `bot.services.prices.get_price`, `native_usd` and `bot.services.market._get` (see existing tests for the pattern).
- `test_live.py` runs real transactions on an in-memory EVM (`eth-tester`) against the contracts in `bot/testdata/Mocks.sol`, which copy the function signatures of Uniswap's routers. If you change `Mocks.sol`, recompile it into `mocks.json` with solc 0.8.26 (optimizer on, 200 runs, `evmVersion: paris`).
- `SelectorTests` check that our ABIs produce the same function selectors as the real contracts. If you add a contract call, add its selector there.

Two dry-run commands talk to mainnet without sending anything (they need an RPC URL saved in Settings or set as an environment variable):

```bash
python manage.py livecheck LINK      # routes, quotes, balances, a simulated buy
python manage.py checktokens         # verified tokens' symbols and decimals match the chain
```

## Common tasks

**Add a verified token.** Add a row to `TOKENS` in a new data migration (see `bot/migrations/0003_seed.py` for the format), with a one-sentence description a beginner understands. Run `python manage.py checktokens` to confirm the address, symbol and decimals. Prefer tokens with deep liquidity on Uniswap.

**Add a network.** A data migration creating a `Network` with its chain ID, `rpc_env` name, explorer, WETH, a USD stablecoin, Uniswap V2/V3 router and quoter addresses, Multicall3 and the GeckoTerminal ID. Then add its verified tokens. Live mode only works where those contracts exist.

**Change or add a guide.** Edit `guides/starter.py`, then add a migration that updates the changed guides (existing installs already have the old text in their database; see how `guides/migrations/0002_seed.py` loads them). Keep the tone: short sentences, plain words, explain every term the first time it appears.

**Add an illustration.** Add a function to `FIGURES` in `guides/figures.py` and reference it as `[[fig:your-name]]` on its own line. The test `test_guides_have_pictures` fails if a guide references a figure that doesn't exist.

**Change a model.** `python manage.py makemigrations` and commit the migration. CI fails if models and migrations are out of sync.

## Style

- **Plain words in the UI.** The app is for beginners. Explain jargon on first use, say what will happen before it happens, and write errors that tell the user what to do next ("No RPC URL yet: open Settings and paste one").
- **Never lose money silently.** Anything in live mode that can fail should fail before signing, with a clear message. New live-mode code needs a test in `test_live.py`.
- **Keep it small.** Django, a little vanilla JS, no frontend framework or build step. Add a dependency only when it clearly pays off.
- **Code.** Follow the style around you: PEP 8, 4 spaces, lines up to ~130 characters, comments that explain *why*. Comments and UI text are in English.

## Pull requests

1. Fork the repo and create a branch: `git checkout -b fix-chart-tooltip`.
2. Make the change, with a test if it changes behaviour.
3. Run `python manage.py test` and `python manage.py makemigrations --check`.
4. For UI changes, add a before/after screenshot to the PR.
5. Open the pull request against `main` and describe what it changes and why.

GitHub Actions runs the tests on every pull request and builds the Windows app. A maintainer will review it; small focused PRs get merged fastest.

## Releases

Maintainers tag a version (`git tag v0.2.0 && git push origin v0.2.0`). The workflow then builds `Pond-windows.zip` and attaches it to a GitHub Release.

By contributing you agree that your contribution is licensed under the [GNU General Public License v3.0 or later](LICENSE).
