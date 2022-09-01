# pyURtimehack

Because [Universal Robots](https://universalrobots.com) do not (currently) support NTP or any other time-sync system despite being based on Debian, this project exists.

All it does is ssh into the robot and set the time based on the host PC, and adds a corresponding note of the action to the UR message log.

## Requirements

A PC that is synced to a timeserver (or not, I guess? You do you) and has network access to one or more Universal Robots.

## Usage

### The Easy Way

1. Run `pyurtimehack.py`
2. Follow the prompts to add one or more robots to the config file
3. Set up a scheduled task on the host to run the script on a regular basis
4. Done!

## The Slightly Harder Way

1. Create a config file by hand in your local app config directory (`AppData` on Windows, probably `.config` on Linux):
```ini
[DEFAULT]
user = root
password = easybot
dashboard_port = 29999
ssh_port = 22
urtz = Europe/Copenhagen
localtz = <YOUR LOCAL IANA TIMEZONE>

[<A ROBOT ENTRY>]
address = <ROBOT IP ADDRESS>
```
2. Follow (#the-easy-way)