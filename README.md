# Caffeine Curfew MCP Server

A local Model Context Protocol server that tracks caffeine decay and predicts safe bedtimes.
All caffeine intake is passed directly as parameters. No external integrations are required.


## How It Works

Caffeine decays according to the standard half-life formula:

    remaining = initial * (0.5 ^ (hours_elapsed / half_life))

The server calculates the sum of that formula across every entry in your intake log to
determine your total current caffeine level and find the earliest time it drops below
your personal sleep interference threshold.

The half-life is adjustable from 3 to 10 hours (default 5).
The sleep interference threshold is adjustable from 10 to 50 mg (default 25 mg).


## Quickstart for Claude Code Users

No installation required. Add this block to your Claude Code MCP settings file and
restart Claude Code. uvx will fetch and run the server automatically on first use.

On macOS the settings file is located at:

    ~/Library/Application Support/Claude/claude_desktop_config.json

```json
{
  "mcpServers": {
    "caffeineCurfew": {
      "command": "uvx",
      "args": ["caffeine-curfew-mcp"]
    }
  }
}
```

That is the only step. The four Caffeine Curfew tools will appear in Claude Code
after restart.


## Tools

### get_caffeine_level

Returns the current total caffeine level in the body.

Parameters:

    entries           list of {amount_mg, consumed_at} intake records
    half_life_hours   float, caffeine half-life in hours (default 5)


### get_safe_bedtime

Returns the earliest time at which caffeine will drop below the threshold.

Parameters:

    entries           list of {amount_mg, consumed_at} intake records
    half_life_hours   float (default 5)
    threshold_mg      float, sleep interference threshold in mg (default 25)


### simulate_drink

Shows how adding a new drink right now would shift the safe bedtime.

Parameters:

    entries           list of {amount_mg, consumed_at} intake records
    half_life_hours   float (default 5)
    threshold_mg      float (default 25)
    new_drink_mg      float, caffeine content of the hypothetical drink in mg


### get_status_summary

Returns a full summary including current level, safe bedtime, and whether a
target bedtime is reachable.

Parameters:

    entries           list of {amount_mg, consumed_at} intake records
    half_life_hours   float (default 5)
    threshold_mg      float (default 25)
    target_bedtime    string, optional ISO 8601 datetime the user wants to sleep by


## Sample Entries for Testing

The timestamps below should be replaced with real ISO 8601 datetimes that are
a few hours before the current time when you run the tests.

```json
[
  {
    "amount_mg": 150,
    "consumed_at": "2025-01-15T08:00:00"
  },
  {
    "amount_mg": 80,
    "consumed_at": "2025-01-15T12:30:00"
  },
  {
    "amount_mg": 100,
    "consumed_at": "2025-01-15T15:00:00"
  }
]
```

The first entry represents a morning coffee (approximately 150 mg).
The second represents a lunchtime espresso (approximately 80 mg).
The third represents an afternoon cold brew (approximately 100 mg).

A typical get_status_summary call with the sample entries and a 10 pm target bedtime:

```json
{
  "entries": [
    {"amount_mg": 150, "consumed_at": "2025-01-15T08:00:00"},
    {"amount_mg": 80,  "consumed_at": "2025-01-15T12:30:00"},
    {"amount_mg": 100, "consumed_at": "2025-01-15T15:00:00"}
  ],
  "half_life_hours": 5,
  "threshold_mg": 25,
  "target_bedtime": "2025-01-15T22:00:00"
}
```


## Remote Deployment (Claude Mobile App)

To use Caffeine Curfew from the Claude iOS or Android app, you need the server running
on a machine that is reachable over the internet with a valid HTTPS URL. A spare Linux
machine on your home network works well for this.

The recommended setup uses Cloudflare Tunnel, which gives you a free persistent HTTPS
URL without opening any ports on your router.


### Step 1: Install the server on Linux

    pip3 install caffeine-curfew-mcp

Or clone the repo and install in editable mode for easier updates:

    git clone https://github.com/YOUR_USERNAME/caffeine-curfew-mcp
    cd caffeine-curfew-mcp
    pip3 install -e .


### Step 2: Install Cloudflare Tunnel

    curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
    sudo dpkg -i cloudflared.deb

Then log in to your Cloudflare account (free account at cloudflare.com is enough):

    cloudflared tunnel login

Create a named tunnel:

    cloudflared tunnel create caffeine-curfew

Note the tunnel ID that is printed. Create a config file at
`~/.cloudflared/config.yml`:

    tunnel: YOUR_TUNNEL_ID
    credentials-file: /home/YOUR_USER/.cloudflared/YOUR_TUNNEL_ID.json

    ingress:
      - hostname: caffeine.yourdomain.com
        service: http://localhost:8000
      - service: http_status:404

Route your domain to the tunnel (requires a domain managed by Cloudflare):

    cloudflared tunnel route dns caffeine-curfew caffeine.yourdomain.com

If you do not have a domain, you can use a temporary public URL for testing:

    cloudflared tunnel --url http://localhost:8000

This prints a random URL like `https://random-words.trycloudflare.com`. It works
immediately but changes every time the process restarts.


### Step 3: Start the server

In one terminal, start the MCP server in SSE mode:

    caffeine-curfew-mcp --transport sse

In another terminal, start the Cloudflare Tunnel:

    cloudflared tunnel run caffeine-curfew

To run both automatically on boot, create systemd services for each. A minimal
service file for the MCP server at `/etc/systemd/system/caffeine-curfew.service`:

    [Unit]
    Description=Caffeine Curfew MCP Server
    After=network.target

    [Service]
    ExecStart=/usr/local/bin/caffeine-curfew-mcp --transport sse
    Restart=always
    User=YOUR_USER

    [Install]
    WantedBy=multi-user.target

Enable and start it:

    sudo systemctl enable caffeine-curfew
    sudo systemctl start caffeine-curfew


### Step 4: Connect in the Claude App

Open the Claude app, go to Settings, then Integrations (or Tools, depending on app
version), and add a new MCP server with the URL:

    https://caffeine.yourdomain.com/sse

The four Caffeine Curfew tools will be available in every conversation.


### Security note

Anyone with the URL can call your server. If you want to restrict access, add a
shared secret by setting an environment variable before starting the server and
putting the Cloudflare Tunnel behind Cloudflare Access (free for personal use),
which adds an authentication layer without changing the server code.


## Local Development Setup

Clone the repository and install in editable mode:

    git clone https://github.com/YOUR_USERNAME/caffeine-curfew-mcp
    cd caffeine-curfew-mcp
    pip3 install -e ".[dev]"

Run the server directly:

    python3 -m caffeine_curfew.server

To point your local Claude Code at a development checkout instead of the published
package, use the python3 form in your MCP settings:

```json
{
  "mcpServers": {
    "caffeineCurfew": {
      "command": "python3",
      "args": ["/absolute/path/to/caffeine-curfew-mcp/caffeine_curfew/server.py"]
    }
  }
}
```


## Publishing to PyPI

Build and upload with standard tooling:

    pip3 install build twine
    python3 -m build
    python3 -m twine upload dist/*

After publishing, any user with uvx installed can connect to the server using
the one-line config shown in the Quickstart section above.


## Notes

Caffeine half-life varies significantly between individuals. Common ranges:

    Average adult          4 to 6 hours
    Oral contraceptives    can double the half-life
    Smokers                roughly half the half-life of non-smokers
    Pregnancy              can extend half-life to 15 hours or more

The default half-life of 5 hours is a reasonable starting point for most adults.
All times returned are provided in both UTC and the local system timezone.
