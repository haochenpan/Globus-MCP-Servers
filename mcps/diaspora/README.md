# Diaspora Octopus MCP Server

A lightweight [FastMCP](https://gofastmcp.com) server that lets Claude (or any MCP-aware agent) publish, consume and administer streams on the **Diaspora Event Fabric**—a Kafka-based data-streaming platform.  The server wraps the official [`diaspora-event-sdk`](https://github.com/globus-labs/diaspora-event-sdk).

## Available Tools

| Category | Tools |
|----------|-------|
| **Auth** | `start_diaspora_login`, `finish_diaspora_login`, `logout` |
| **Credentials** | `create_key` (rotates MSK IAM secret) |
| **Topics** | `list_topics`, `register_topic`, `unregister_topic` |
| **Data plane** | `send_event`, `consume_latest_event` |


## Prerequisites

- Python 3.11
- A Globus account (sign up at [globus.org](https://www.globus.org/))
- Globus Client ID (register an app at [developers.globus.org](https://developers.globus.org/))
- Claude Desktop application

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/globus-labs/science-mcps
   cd science-mcps/mcps/diaspora
   ```

2. Create a conda environment:
   ```bash
   conda create -n science-mcps python=3.11
   conda activate science-mcps
   ```

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
