# Experiments

This directory contains scripts for running FHIR agent evaluation experiments.

---

## Files

| File | Description |
|------|-------------|
| `run_experiment_fhir.py` | Main experiment runner - evaluates multiple agent configurations |
| `verify_modular_tasks.py` | Validates modular task implementations |
| `start_servers.sh` | Starts all required MCP servers |

---

## Prerequisites

Before running experiments, ensure you have:

1. **Python environment** with dependencies installed:
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment variables** configured in `environment/.env`:
   ```env
   OPENAI_API_KEY=sk-...
   ```

3. **HAPI FHIR server** running via Docker:
   ```bash
   cd environment/hapi-fhir
   docker-compose up -d
   ```
   The server runs on `http://localhost:7070/fhir`.

4. **MCP servers** running (see below).

---

## Starting MCP Servers

`run_experiment_fhir.py` needs 4 MCP servers running:

| Server | Port | Endpoint | Purpose |
|--------|------|----------|---------|
| FHIR MCP | 8000 | `/fhir_mcp` | FHIR CRUD operations |
| FHIR Specs | 8010 | `/fhir_specs` | FHIR specification lookups |
| Memory (no-spec) | 8011 | `/memory_fig_3_no_spec` | Retrieval from no-spec training |
| Memory (with-spec) | 8012 | `/memory_fig_3_with_spec` | Retrieval from with-spec training |

### Option 1: Use the Script (Recommended)

```bash
chmod +x start_servers.sh
./start_servers.sh
```

This starts all 4 servers in the foreground with color-coded logs. Press `Ctrl+C` to stop all servers.

### Option 2: Start Manually

If you prefer to run each server in separate terminals:

```bash
# Terminal 1 - FHIR MCP
cd environment/mcp/baseline_server
python fhir_mcp_server.py --port 8000 --path /fhir_mcp

# Terminal 2 - FHIR Specs
cd environment/mcp/memory_servers
python fhir_ref_mcp_server.py --port 8010 --path /fhir_specs

# Terminal 3 - Memory (no-spec training)
cd environment/mcp/memory_servers
python fhir_memory_mcp_server.py --port 8011 --ltm-dir exp_fig_3_no_spec --path /memory_fig_3_no_spec

# Terminal 4 - Memory (with-spec training)
cd environment/mcp/memory_servers
python fhir_memory_mcp_server.py --port 8012 --ltm-dir exp_fig_3_with_spec --path /memory_fig_3_with_spec
```

---

## Running Experiments

Once prerequisites are ready:

```bash
python run_experiment_fhir.py \
    --variations-yaml environment/data/exp_1_task_variation_updated.yaml \
    --output-dir results/my_experiment
```

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--variations-yaml` | `exp_1_task_variation_updated.yaml` | Path to task variations YAML |
| `--output-dir` | (required) | Directory to write results |
| `--model` | `openai:gpt-4.1-mini` | OpenAI model to use |
| `--fhir-sse-url` | `http://localhost:8000/fhir_mcp` | FHIR MCP endpoint |
| `--paraphrase` | `False` | Enable prompt paraphrasing |

### Agent Configurations Evaluated

The experiment evaluates 5 agent configurations:

1. **baseline_nomemory** — No tools beyond FHIR
2. **baseline_with_references** — FHIR + spec lookups
3. **baseline_with_memory_no_spec** — FHIR + memory (no-spec trained)
4. **baseline_mem_spec_trained** — FHIR + memory (spec-trained, no runtime specs)
5. **baseline_with_memory_and_references** — FHIR + memory + specs

---

## Output

Results are written to `--output-dir` with:

- Per-task JSON logs with execution traces
- Agent reasoning and tool calls
- Validation results

---

## Quick Start Summary

```bash
# 1. Start FHIR server (from project root)
cd environment/hapi-fhir && docker-compose up -d && cd ../..

# 2. Start MCP servers (from project root)
cd experiments
chmod +x start_servers.sh
./start_servers.sh

# 3. Run experiment (in a new terminal, from experiments/)
python run_experiment_fhir.py \
    --variations-yaml environment/data/exp_1_task_variation_updated.yaml \
    --output-dir results/my_run
```

---

## What `start_servers.sh` Does

The script automates MCP server startup:

1. **Checks prerequisites**: Python installed, `.env` exists, FHIR server responding
2. **Starts 4 MCP servers** with color-coded log output:
   - `fhir_mcp_server.py` on port 8000 (green)
   - `fhir_ref_mcp_server.py` on port 8010 (cyan)
   - `fhir_memory_mcp_server.py` on port 8011 - no-spec memory (yellow)
   - `fhir_memory_mcp_server.py` on port 8012 - with-spec memory (magenta)
3. **Skips ports** already in use to avoid conflicts
4. **Handles cleanup** on `Ctrl+C` — stops all servers gracefully

To run it:
```bash
./start_servers.sh   # Start all servers (foreground with logs)
# Press Ctrl+C to stop
```

