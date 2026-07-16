# Remote deployment bundle

A self-contained subset of the project that runs the HAPI FHIR server and the
four MCP servers the benchmark agents talk to. Copy this folder to a VPS (or
any remote host) and start the services there. The harness on your laptop
drives the experiment over SSH.

This bundle does **not** contain the agent code, the runners, the prompts,
the task source, the expected-tool-call answer keys, or the variation YAMLs.
Keeping those off the remote host is intentional: it prevents the agent under
test from reading them and gaming the benchmark.

## Layout

```
environment/
  .env.example                   # copy to environment/.env, fill OPENAI_API_KEY
  hapi-fhir/docker-compose.yml   # HAPI FHIR R4 server (port 7070)
  data/
    fhir_res_ref_all/            # FHIR R4 resource StructureDefinitions
    fhir_datatypes_ref/          # FHIR R4 datatype StructureDefinitions
  indexes/reflexion_faiss/
    exp_fig_3_no_spec/           # Reflexion memory store, no-spec config
    exp_fig_3_with_spec/         # Reflexion memory store, with-spec config
  mcp/
    baseline_server/fhir_mcp_server.py        # :8000  /fhir_mcp
    memory_servers/
      fhir_ref_mcp_server.py                  # :8010  /fhir_specs
      fhir_memory_mcp_server.py               # :8011 + :8012  /memory_fig_3_*
      memory_stores/fhir_reflexion_memory_store.py
experiments/
  start_servers.sh               # spawns the four MCP servers
requirements.txt                 # bundle-only Python deps
```

## Deploy

Run these from the project root on your laptop. `remote-deployment-bundle/` is
this folder. Replace `user@host` with your VPS login.

```bash
# 1. Copy the bundle to the host.
#    rsync is fastest, but anything works — scp, an SFTP client,
#    or just dragging the folder onto the VPS in a file manager. The
#    only requirement is that the bundle ends up at ~/fhir-eval/ on the host.
rsync -avh remote-deployment-bundle/ user@host:~/fhir-eval/

# 2. SSH in
ssh user@host
cd ~/fhir-eval

# 3. Secrets
cp environment/.env.example environment/.env
$EDITOR environment/.env       # set OPENAI_API_KEY

# 4. Python venv + deps
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 5. Start HAPI FHIR
cd environment/hapi-fhir && docker-compose up -d && cd ../..

# 6. Start the MCP servers (foreground; Ctrl+C stops all)
./experiments/start_servers.sh
```

## Endpoints

Once `start_servers.sh` is running, the host is listening on:

- `http://localhost:7070/fhir`                     — HAPI FHIR
- `http://localhost:8000/fhir_mcp`                 — FHIR MCP
- `http://localhost:8010/fhir_specs`               — Specs MCP
- `http://localhost:8011/memory_fig_3_no_spec`     — Memory MCP (no-spec)
- `http://localhost:8012/memory_fig_3_with_spec`   — Memory MCP (with-spec)

These match the URLs in `experiments/claude_code_configs/*.json` in the main
repo. When the harness runs `claude -p` over SSH, Claude Code resolves them
via localhost on this host.

For the harness to reach HAPI from your laptop (for test data setup and
validation), set `FHIR_SERVER_URL` in your local `environment/.env` to
`http://<host-ip>:7070/fhir` and make sure port 7070 is reachable.

## Giving Claude Code more MCP servers

The Claude Code runner reads its MCP config from
`experiments/claude_code_configs/claude_code.json` in the main repo, inlines
it into the `claude -p --mcp-config <…>` invocation, and derives the allowed
tool list from the `mcpServers` keys. By default it only wires the FHIR MCP:

```json
{
  "mcpServers": {
    "fhir": { "type": "sse", "url": "http://localhost:8000/fhir_mcp" }
  }
}
```

To give Claude Code access to the specs or memory servers that this bundle
already runs, add them as extra entries. No code changes needed.

```json
{
  "mcpServers": {
    "fhir":   { "type": "sse", "url": "http://localhost:8000/fhir_mcp" },
    "specs":  { "type": "sse", "url": "http://localhost:8010/fhir_specs" },
    "memory": { "type": "sse", "url": "http://localhost:8011/memory_fig_3_no_spec" }
  }
}
```

The URLs are resolved on whichever host runs `claude -p` — the VPS in remote
mode, your laptop in local mode — so `localhost` is correct in both cases.
