"""Guides that ship with the app. A migration loads them into the database; after that they can be edited in the admin.

A [[fig:name]] line inserts an illustration from guides/figures.py.
"""

GUIDES = [
    {
        "slug": "rpc-keys", "level": "novice", "minutes": 3, "order": 5,
        "title": "Getting an RPC key",
        "summary": "The free link the app uses to see the blockchain. Three minutes.",
        "body": """
The app doesn't store the blockchain itself. It reads prices and balances and sends trades through a **node**: a server with a copy of the blockchain. The node's address is called an **RPC** URL (Remote Procedure Call). It's a regular link like `https://…/your-key`.

You don't need to run a node yourself: providers give you one, and all of them have a free plan. For a single person it is more than enough.

## Where to get one

Any of these providers will do: **Alchemy**, **Infura**, **dRPC**, **QuickNode**, **Chainstack**. The steps are almost the same everywhere:

1. Sign up on the provider's website (email or GitHub).
2. Create an app or a key. The button is called something like "Create app", "Create API key" or "Create endpoint".
3. Pick the **Ethereum Mainnet** network. Not Sepolia or Holesky: those are testnets with play money.
4. Copy the **HTTPS** link. A WSS link (`wss://…`) won't work.
5. In the app, open **Settings → Network connection**, paste the link and click "Save and test".

If everything is right, the app says "the node works" and shows the latest block number.

## Is it safe

- The link contains your personal key for the provider. Don't publish it, or someone else can burn through your free quota.
- This key gives no access to your money. Money is protected by the wallet's private key, which never goes to the provider: trades are signed on your computer.
- The link is stored only on your computer, in the app's data folder.

## If the test shows an error

| Message | What to do |
|---|---|
| "Use the link that starts with https://" | you copied the wss:// link; take the HTTPS one |
| "it is a different network" | you picked a testnet; create a key for Ethereum Mainnet |
| "The node refused access" | the key was not copied in full or is not activated yet |
| "The node did not answer" | no internet, or the provider is down; try again later |

## What it costs

Nothing, as long as you trade for yourself. The app caches prices and doesn't make extra requests. A paid plan only makes sense if you run many bots or watch hundreds of tokens.
""",
    },
    {
        "slug": "start", "level": "novice", "minutes": 2, "order": 10,
        "title": "First steps",
        "summary": "How everything works here and what to click first.",
        "body": """
Here you can trade tokens by hand or leave it to the bot. Start in **demo mode**: the money is not real, but the prices are, straight from the exchange.

## Three steps

1. Open **Trade**, pick a token and buy a little. You have 1 demo ETH.
2. Go back to **Pond**: it shows what everything you bought is worth right now.
3. Open **Rules** and set your first one, for example "when the price drops below X, buy". The bot watches the price and does it for you.

## What's where

- **Pond**: your balance, positions and recent trades.
- **Trade**: buy or sell right now.
- **Rules**: orders for the bot to carry out later.
- **Wallet**: a separate trading wallet for real money.
- **Settings**: your RPC key, live trading, limits and password.

Don't rush into real money. Trade in demo for a week first and look at the result.
""",
    },
    {
        "slug": "swap", "level": "novice", "minutes": 3, "order": 20,
        "title": "What a swap and a DEX are",
        "summary": "Where the price comes from and who you are buying from.",
        "body": """
A **DEX** (decentralized exchange) is an exchange with no company in the middle. It's a program on the blockchain that swaps one token for another. The best known one is Uniswap.

A **swap** is the exchange itself: you give ETH and get a token, or the other way round.

## Who am I buying from?

Not from a person, but from a **liquidity pool**. A pool is a shared pot holding two tokens, for example ETH and PEPE. You put ETH into the pot and take PEPE out.

## Where does the price come from?

From the ratio of tokens in the pot. You bought PEPE, so there is less PEPE in the pot and more ETH, and PEPE got more expensive. The smaller the pot, the more your purchase moves the price.

## What follows from this

- In a big pool the price is stable; in a small one it jumps with every trade.
- The pool takes a fee on every swap, usually 0.3 %.
- A token without a pool can't be bought or sold.
""",
    },
    {
        "slug": "gas-slippage", "level": "novice", "minutes": 3, "order": 30,
        "title": "Gas and slippage",
        "summary": "Two things that make a trade cost more than expected.",
        "body": """
## Gas

**Gas** is the fee the network charges to execute a trade. It is paid in ETH and doesn't depend on the amount: a $10 swap and a $10,000 swap cost about the same.

So small trades on Ethereum don't pay off. If gas costs $3 and you buy for $20, you start 15 % down.

## Slippage

**Slippage** is the difference between the price you saw and the price your trade actually got. There are two reasons:

- someone else bought before you while your trade was waiting for a block;
- your own trade moved the price in the pool.

When you swap you set a tolerance, for example 1 %. If the price moves further, the trade is cancelled, but the gas is still spent.

## In demo mode

The 0.3 % pool fee is included; gas and slippage are not. Real results will be a bit worse than demo.
""",
    },
    {
        "slug": "chart-reading", "level": "novice", "minutes": 6, "order": 35,
        "title": "Reading candles and the chart",
        "summary": "What a candle is made of, why it \"grows in place\", what timeframes and volume are.",
        "body": """
The chart shows how the token's price in dollars has changed. Before a trade it answers the main question: is it expensive or cheap right now compared to the recent past?

## What a candle is made of

One candle is one period of time: 15 minutes, an hour, a day. Everything the price did in that period is squeezed into four numbers.

[[fig:candle-anatomy]]

- **Open**: the price at the start of the period.
- **Close**: the price at the end.
- **High and low**: how far the price went up and down.

The **body** is the thick part between the open and the close. The **wicks** are the thin lines to the high and the low.

A green candle closed above its open: the price went up. A red one closed below: the price went down.

## What the candle's shape says

[[fig:candle-shapes]]

- **Long body**: one side clearly won. Green means buyers, red means sellers.
- **Short body**: the price barely moved, the market is waiting.
- **Long lower wick**: the price was pushed down but bought back. There are buyers below.
- **Long upper wick**: the price was pushed up but sold back. There are sellers above.

A single candle is a hint, not a signal. Look at several in a row.

## Why a candle "grows in place"

This is the least intuitive thing at first. **The last candle isn't finished yet.** Until its time is up it changes in place: it stretches, shrinks, changes color. The chart is not frozen.

- On the **1h** timeframe a new candle appears once an hour. The rest of the time the current one is moving.
- On **1d** the same candle lives for a whole day.
- If the price doesn't move, the candle doesn't either. That's not a bug, just a quiet market.

Above our chart it says **when the current candle closes**, and under the price it says when it was last updated. If the counter is running, everything works.

Want to see movement more often? Switch to **15m**.

## Timeframe

The timeframe is how much time one candle covers. The buttons above the chart: **15m, 1h, 4h, 1d**.

| Timeframe | What you see | What it's for |
|---|---|---|
| 1d | months | the overall direction |
| 4h | weeks | finding important levels |
| 1h | a few days | choosing an entry price |
| 15m | the last hours | the exact moment to trade |

Rule of thumb: **big timeframe first, then the small one.** On 15 minutes a rise can look powerful while on the daily chart it's a tiny bounce in the middle of a fall.

## Volume

The bars at the bottom show how many dollars were traded during each candle.

- A price rise **on high volume** has real buying behind it and is more reliable.
- A rise **on low volume** has few buyers and can easily reverse.
- A sudden volume spike after a long fall often means the sellers are exhausted.

## What's drawn on our chart

- **Dashed lines** are your rules: green for buying, orange for selling.
- **The dotted line** is your average entry price. Above it, you're in profit.
- **Arrows** are your trades.
- Click the chart at the price you want and a "set a rule at this price" button appears. The click itself buys nothing.

## The summary above the chart

- **24h change**: how much the price changed in percent.
- **24h volume**: how much was traded.
- **Liquidity**: how much money sits in the pool. Below $50K even your trade will noticeably move the price.

## Common mistakes

- Looking only at 15 minutes without knowing what the daily chart says.
- Buying on a long green candle "before it runs away". A pullback usually follows.
- Treating an unfinished candle as a ready signal: it can still flip before it closes.

Next: "Candlestick patterns" and "Chart patterns".
""",
    },
    {
        "slug": "candle-models", "level": "novice", "minutes": 5, "order": 37,
        "title": "Candlestick patterns: hammer, engulfing, doji",
        "summary": "A few candles in a row that hint at a reversal. With pictures.",
        "body": """
A candlestick pattern is one to three candles of a typical shape. It shows that the balance between buyers and sellers is changing.

A pattern only matters **in the right place**: a hammer in the middle of a sideways range means nothing, a hammer after a long fall at a support level is worth a look.

## Hammer and shooting star

[[fig:model-hammer-star]]

**Hammer**: a small body at the top and a long lower wick, at least twice the body. The price was pushed down hard but bought back by the close. It appears after a fall and hints at a reversal up.

**Shooting star**: the opposite. A small body at the bottom and a long upper wick. The price was pushed up but sold back. It appears after a rise and hints at a reversal down.

The body's color hardly matters for either; the long wick does.

## Engulfing

[[fig:model-engulfing]]

Two candles. The second points the other way and its body **fully covers** the body of the first.

- **Bullish engulfing** (after a fall): a small red candle, then a big green one. Buyers took over.
- **Bearish engulfing** (after a rise): a small green candle, then a big red one. Sellers took over.

"Bullish" and "bearish" are jargon: bulls buy and push the price up, bears sell and push it down.

## Doji

[[fig:model-doji]]

A candle whose open and close almost match: no body, only wicks. The market hasn't decided.

A doji doesn't tell you where the price goes next. It tells you the previous move has lost strength. The next candle shows the direction.

## How to use them

1. **Location first.** The pattern should come after a noticeable move, ideally at a support or resistance level.
2. **Wait for the candle to close.** Until then a hammer can turn into an ordinary red candle.
3. **Wait for confirmation.** The next candle should move in the signal's direction.
4. **Check the volume.** A pattern on high volume carries more weight.
5. **Use 1h and above.** On 15 minutes there are lots of patterns and most of them are noise.

| Pattern | Where it appears | What it hints at | Bot rule |
|---|---|---|---|
| Hammer | at the bottom, after a fall | a rise | buy a bit above the hammer's high, stop below its low |
| Shooting star | at the top, after a rise | a drop | sell part, stop-loss below the star's low |
| Bullish engulfing | at the bottom | a rise | buy, stop below the pattern's low |
| Bearish engulfing | at the top | a drop | sell part or tighten the stop-loss |
| Doji | anywhere | indecision | do nothing, wait for the next candle |

## An honest warning

Candlestick patterns don't always work: by various counts, only somewhat more often than half the time. They don't predict the price; they help you pick a moment when the risk is clear. If the pattern fails, you exit at the stop-loss with a small loss.
""",
    },
    {
        "slug": "bot-rules", "level": "novice", "minutes": 4, "order": 40,
        "title": "Bot rules: three recipes",
        "summary": "Buying the dip, taking profit and the stop-loss.",
        "body": """
A rule is an order: **when the token's price drops below or rises above X, buy or sell**. The bot checks the price every few seconds.

## 1. Buy the dip

*When the price drops below X, buy for amount Y.*

You think the token is good but expensive right now. You set the price you're willing to pay and don't have to sit by the chart.

## 2. Take profit

*When the price rises above X, sell 50 %.*

You sell part of the position into the rise. Half of the profit is already yours, and the other half keeps growing if the rise isn't over.

## 3. Stop-loss

*When the price drops below X, sell 100 %.*

You decide in advance what loss you're willing to accept. Without a stop, "I'll wait for it to bounce" easily turns into minus 80 %.

## Putting them together

People put two rules on one position: take profit above and a stop-loss below. Then both outcomes of the trade are known in advance.

## Details

- A normal rule fires once and switches off.
- With "Repeat" ticked it fires again, but no more than once an hour.
- The bot works only while the app is open.
""",
    },
    {
        "slug": "scam-tokens", "level": "novice", "minutes": 3, "order": 50,
        "title": "Scam tokens",
        "summary": "Honeypots, rug pulls and how not to buy junk.",
        "body": """
Anyone can create a token in five minutes, so most new tokens are junk or traps.

## Honeypot

The token can be bought but not sold: selling is blocked in the contract's code. The chart shows only buys and a pretty rise.

## Rug pull

The creator pulls the liquidity out of the pool or dumps a huge stash of tokens. The price falls to almost zero within a minute.

## Trading tax

The contract charges a fee on every buy and sell, sometimes 20–50 %. The author can raise it after you buy.

## How to check

- Is anyone besides the creator selling? If there are no sells, it's a honeypot.
- How much liquidity is in the pool, and is it locked?
- How many tokens do the ten biggest holders have?
- Fakes copy the symbol of a well-known token. Compare the **contract address**, not the name.

Tokens in our list are verified. Anything you add by address yourself is at your own risk.
""",
    },
    {
        "slug": "patterns", "level": "pro", "minutes": 8, "order": 60,
        "title": "Chart patterns",
        "summary": "Trend, levels, breakouts, double top, head and shoulders, flags. With pictures and rules.",
        "body": """
A pattern is a recurring shape in the price. It's not a guarantee but a reason for a bet whose risk you know in advance. If you haven't read "Reading candles and the chart" yet, start there.

## Trend

[[fig:trend]]

- **Uptrend**: each pullback ends higher than the previous one.
- **Downtrend**: each bounce ends lower than the previous one.
- **Sideways** (range): the price moves in a corridor between two levels.

Trading with the trend is easier than against it. In an uptrend people buy the pullbacks; in a range, near the lower edge.

## Support and resistance

[[fig:levels]]

**Support** is a level the price has bounced up from several times: buyers wait there. **Resistance** is a level it has turned down from: sellers wait there.

A level is a zone, not an exact number. The more touches and the bigger the timeframe, the more the level matters.

## Breakout

[[fig:breakout]]

The price clears a level with conviction, on high volume. After that the level **switches roles**: broken resistance becomes support. Often the price comes back to test it (a retest) and then moves on.

It's safer to buy the retest than the breakout itself: the price is better and the stop-loss is closer.

## False breakout

[[fig:false-breakout]]

The price pokes past the level and quickly comes back. On small tokens this happens all the time: a big player pushes the price over the level, collects the buy orders of everyone waiting for the breakout and sells to them.

Protection: wait for a candle to close beyond the level and check the volume. A breakout without volume is suspicious.

## Double top and double bottom

[[fig:double]]

The price hits the same level twice and can't get through. The pattern is complete when the price breaks the line between the two peaks (or the two lows).

- **Double top**: a signal to fall.
- **Double bottom**: a signal to rise.

## Head and shoulders

[[fig:head-shoulders]]

Three peaks: the middle one (the "head") is higher than the ones on the sides (the "shoulders"). The line through the lows between them is the **neckline**. A break below the neckline signals that the rise is over. There's also an inverted version at the bottom that signals a rise.

## Triangle and flag

[[fig:triangle-flag]]

These are **continuation** patterns: the price rests and then keeps going the same way.

- **Triangle**: the swings get narrower. The closer to the tip, the sooner the breakout. Trade in the direction of the breakout.
- **Flag**: after a sharp move the price drifts a little in a narrow channel, then continues.

## The trade plan

[[fig:plan]]

Every pattern comes down to three prices you know **before entering**:

1. **Entry**: where I buy.
2. **Stop-loss**: where I admit I was wrong.
3. **Target**: where I take profit.

Take trades where the target is at least twice as far from the entry as the stop. Then being right in 4 trades out of 10 is enough.

## Turning it into bot rules

| Idea | Rules |
|---|---|
| Bounce off support | buy a bit above the level · stop-loss a bit below · sell half near resistance |
| Resistance breakout | buy when the price is above the level · stop-loss below the level |
| Double bottom | buy above the line between the lows · stop-loss below the bottom |
| Head and shoulders | sell when the price drops below the neckline |
| Bull flag | buy above the flag's upper edge · stop-loss below its lower edge |

On the trade page, click the chart at the level you want and the rule form opens with that price.

## Limitations

- Patterns don't always work. Without a stop-loss, one failed pattern eats the profit of several good ones.
- On tokens with a small pool, levels work worse: one big player moves the price however they like.
- The 15-minute chart has more "patterns" than meaning. Look for them on 1h and above.
- Test the idea in demo before putting real money on it.
""",
    },
    {
        "slug": "risk", "level": "pro", "minutes": 4, "order": 70,
        "title": "Risk management",
        "summary": "How much to bet per trade so that a losing streak doesn't wipe you out.",
        "body": """
Whether you make money depends less on how often you're right than on how much you lose when you're wrong.

## The 1–2 % rule

Risk no more than 1–2 % of your account on one trade. The risk is not the amount you buy for, but the loss if the stop-loss is hit.

Example: an account of 1 ETH, 2 % risk = 0.02 ETH. The stop is 10 % below the buy price. So you can buy for 0.02 / 0.10 = 0.2 ETH.

## Risk/reward ratio

Take trades where the possible profit is at least twice the risk (2:1). Then being right in 4 trades out of 10 is enough to stay in profit.

## Losses are asymmetric

| You lose | You need to gain to get back |
|---|---|
| 10 % | 11 % |
| 50 % | 100 % |
| 80 % | 400 % |

That's why the stop-loss matters more than a good entry.

## In practice

- Don't keep your whole account in one token.
- Don't increase your bet to "win it back".
- Only put in what you're ready to lose completely.
- Write down why you entered a trade and compare it with the outcome.
""",
    },
]
