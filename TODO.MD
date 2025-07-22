# TODO.md

Here's a list of instructions/prompts for a Claude AI agent, derived from the current tasks, along with a simple template for adding new tasks.

## Claude Code Agent Instructions

Use these instructions as prompts to guide your work on the project:

- [ ] seems like the datamanager reinit is not working properly (press ctrl+f to reset the channnels count but not worked, also it should automatically reset since the setting is enabled but it is not), fix it.

- [ ] On UI, in zmq side, show the data recirved status (show if data recived timeout is reached

- [ ] On UI, in zmq side, show the auto reinit setting and status when occured (when the data recieved timeout is reached)

- [ ] the delay show in OSC side is good but when the data is not send from zmq it should show the delay as 0 (with some * or any sign to indicate that the data is not received)

- [ ] the sampling rate on osc side should be shown as 0 when the data is not received from zmq (with some * or any sign to indicate that the data is not received), during the startup it should be shown both current rate and mean rate (mean rate should be calculated from the last 10 seconds)



