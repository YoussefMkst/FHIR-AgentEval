# Droplet bundle

Self-contained subset of the project for running HAPI FHIR + the 4 MCP servers
on a droplet.

## What's inside

```
environment/
  .env.example                   # copy to environment/.env, fill OPENAI_API_KEY
  hapi-fhir/docker-compose.yml   # HAPI FHIR R4 server (port 7070)
  data/
    fhir_res_ref_all/            # FHIR R4 resource StructureDefinitions
    fhir_datatypes_ref/          # FHIR R4 datatype StructureDefinitions
  indexes/reflexion_faiss/
    exp_fig_3_no_spec/           # Reflexion memory store for the no-spec config
    exp_fig_3_with_spec/         # Reflexion memory store for the with-spec config
  mcp/
    baseline_server/fhir_mcp_server.py        # :8000  /fhir_mcp
    memory_servers/
      fhir_ref_mcp_server.py                  # :8010  /fhir_specs
      fhir_memory_mcp_server.py               # :8011 + :8012  /memory_fig_3_*
      memory_stores/fhir_reflexion_memory_store.py
experiments/
  start_servers.sh               # spawns the 4 MCP servers
requirements.txt                 # droplet-only Python deps
```

What is intentionally NOT here: the agent code, the runners, the prompts, the
task source, the expected-tool-call answer keys, the variation YAMLs. The
benchmark harness lives on your local machine and only sends task prompts to
Claude Code over SSH; it never copies task ground-truth to the droplet.

## Setup on the droplet

```bash
# Upload this directory (renamed however you like):
rsync -avh ./<this-dir>/ user@droplet:~/fhir-eval/

ssh user@droplet
cd ~/fhir-eval

# 1. Secrets
cp environment/.env.example environment/.env
$EDITOR environment/.env       # set OPENAI_API_KEY

# 2. Python venv + deps
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. HAPI FHIR (Docker)
cd environment/hapi-fhir && docker-compose up -d && cd ../..

# 4. MCP servers (foreground; Ctrl+C to stop all)
./experiments/start_servers.sh
```

After that the droplet is listening on:
- `http://localhost:7070/fhir`               (HAPI)
- `http://localhost:8000/fhir_mcp`           (FHIR MCP)
- `http://localhost:8010/fhir_specs`         (Specs MCP)
- `http://localhost:8011/memory_fig_3_no_spec`   (Memory MCP, no-spec training)
- `http://localhost:8012/memory_fig_3_with_spec` (Memory MCP, with-spec training)

Those are exactly the URLs in `experiments/claude_code_configs/*.json` on the
local repo, so Claude Code resolves them via localhost on the droplet.
