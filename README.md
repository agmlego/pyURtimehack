# pyURtimehack

Because [Universal Robots](https://universalrobots.com) do not (currently) support NTP or any other time-sync system despite being based on Debian, this project exists.

## Requirements

A PC that is synced to a timeserver (or not, I guess? You do you) and has network access to one or more Universal Robots.

## Usage

### The Easy Way

1. Run `pyurtimehack.py`
2. Follow the prompts to add one or more robots to the config file
3. Set up a scheduled task on the host to run the script on a regular basis
4. Done!

## The Slightly Harder Way

1. Create a config file by hand in your local app config directory (`AppData` on Windows, probably `.config` on Linux)
2. Follow (#the-easy-way)