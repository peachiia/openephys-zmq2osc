# TODO.md

Here's a list of instructions/prompts for a Claude AI agent, derived from the current tasks, along with a simple template for adding new tasks.

## Claude Code Agent Instructions

Use these instructions as prompts to guide your work on the project:

- [ ] in "Receiving (5 Secs.)" replace with shorter "Receiving (5.0s)" instead, and replace that number with number from the code or the setting (number must be chabge if the actual setting changed). Also change the default number to 2.0 seconds in the code and the setting.

- [ ] right now the OSC sampling rate and the delay calculation is not reset to zero when data is not reached from zmq so please reset all those number to 0 when re-init function is called.

- [ ] Show the estimated ZMQ data sampling delay (Chunk Delay) by the sampling rate divided by the size of the package (one data chunk) so we can see how much delay we have in the data flow. Show the number over the data receiving status in the GUI. The number should be shown in milliseconds and should be updated every second. Don't have to show color coding for the delay, just show the number.

