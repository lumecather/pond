# Security

Pond holds the private key of a trading wallet, so security bugs matter.

**Please don't open a public issue for a vulnerability.** Report it privately through
GitHub: the repository's **Security** tab → **Report a vulnerability**.

## How keys are protected

- The trading wallet's private key is encrypted with a key derived from your password (scrypt + Fernet).
  The password and the derived key are never written to disk.
- The app's web server listens on `127.0.0.1` only, and only the app window can log in
  (a random token is created on every launch).
- Live trades are simulated with `eth_estimate_gas` before they are signed, buys are capped by a
  per-trade limit, and withdrawals only go to the address you set in Settings.

## What it doesn't protect against

Malware on your computer can read memory or log keystrokes while Pond is unlocked.
Use a separate wallet for the bot and keep only what you're ready to risk in it.
