# gta6-forecast

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/imusic-487/gta6-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/imusic-487/gta6-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

A launch-day shape forecaster for make.fun's `gta6-twitch-ccu-forecast-01`
bounty. It forecasts Grand Theft Auto VI's Twitch concurrent viewers hour by
hour (hours 2–24 of release day, 2026-11-19 UTC) as five quantiles per hour,
learned from the past big launches the case hands over as comparables.

## Method

The house baseline says every hour stays at hour 1's print. A real console
launch does not stay flat: viewers dip through the small hours, then climb as
the UK unlocks at midnight UTC, the US east coast at 05:00 UTC and the west
coast at 08:00 UTC, and peak in the US evening (hours 20–21). The program
learns that shape from the comparables:

- Each comparable's launch-day curve is normalised by its hour-1 count.
- The relevant set is the comparables with a real launch hour (hour-1
  viewers ≥ 10,000). Games below that had not unlocked anywhere by 00:00 UTC
  and explode 100–2000× later in the day; they belong to a different unlock
  structure. Console-only launches (no PC) are preferred when at least five
  exist, and the case's own game is excluded by name.
- Per hour, the median is the relevant set's median ratio; the spread is
  lognormal with log-sd from the ratios pooled across every big launch
  (the relevant set alone is too small for its own interquartile range to say
  how far a launch day can run from its median shape).
- Size flattening: the bigger hour 1 is, the flatter the launch day
  (log(peak / hour 1) = 3.755 − 0.260 · log(hour 1) on the console-only set).
  A record hour 1 flattens the whole curve toward 1.0.

Anything unusable falls back to the persistence baseline for that hour, so a
case is always valid. No network, no randomness, no clock: two runs write the
same bytes.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

## Validation

The practice scorer is server-only, so the entry was validated by
leave-one-out over the 28 comparable launches with a real hour 1 (each game
as a pseudo-case, its own curve the truth, never in its own training set):

| | loss (mean pinball, log scale) | typical miss | 90% coverage |
| --- | --- | --- | --- |
| this entry, all 28 | 0.296 | 59.2% | 0.811 |
| house baseline, all 28 | 0.351 | 69.0% | 0.766 |
| this entry, console-only (n=7) | 0.186 | 34.1% | 0.969 |
| house baseline, console-only | 0.283 | 58.8% | 0.839 |

The console-only set is the Grand Theft Auto VI-like population (console-only,
rolling midnight-local unlock); there the entry beats the baseline's loss by
about a third. The house baseline scores about 0.387 on the practice cases.

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
