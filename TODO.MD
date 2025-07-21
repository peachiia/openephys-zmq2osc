# TODO.md

Here's a list of instructions/prompts for a Claude AI agent, derived from the current tasks, along with a simple template for adding new tasks.

## Claude Code Agent Instructions

Use these instructions as prompts to guide your work on the project:

- [ ] Resolve Binary Runtime Error: Investigate and fix the error that occurs when running the binary built by build.py. Ensure the application executes successfully.

- [ ] Clean Up num_channels: Locate and remove all instances of num_channels: int = 32 from the codebase and update the README to reflect this change, as channel detection is now automatic.

- [ ] Fix ZMQ Channel Name Display: Implement a solution to correctly display ZMQ channel names in the UI, as they are currently appearing as empty.

- [ ] Analyze and Display OSC Delay:

  - Examine the cause of the data delay and buffering on the OSC side, specifically when streaming multiple channels, and address why data persists after ZMQ streaming stops.

  - Develop and integrate a mechanism to accurately calculate the actual delay in OSC data transmission.

  - Ensure this calculated delay is clearly displayed in the UI.

- [ ] Dynamic OSC Sampling Rate: Modify the OSC-side UI to dynamically calculate and display the actual sampling rate based on the incoming data, instead of using a fixed value.

- [ ] Display OSC Channel Mapping: Add a UI element (e.g., a tree or list) to show the mapping between channel names and their corresponding OSC channels.

- [ ] Clock in UI seems to display and update every 2 sends instead of every second. Investigate and fix this issue to ensure the clock updates correctly. Is the UI refresh rate is correctly implemented and functioning as intended?
