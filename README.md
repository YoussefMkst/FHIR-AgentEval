# FHIR-AgentEval

## Overview
FHIR-AgentEval is a modular sandbox for evaluating LLM agents on end-to-end HL7 FHIR workflows. It includes a curated benchmark of 43 reusable clinical tasks spanning appointment management and genetic testing scenarios, where each task combines a prompt template, deterministic validation, and task-specific environment seeding against a resettable HAPI FHIR server. Agents interact with the server through a lightweight MCP layer that exposes only core FHIR CRUD tools, which keeps the setup model- and framework-agnostic.
On top of this core sandbox, we include optional add-ons that can be enabled, most notably an on-demand FHIR R4 specifications server for runtime lookups and a Reflexion-inspired long-term memory server distilled offline, with or without spec grounding. The sandbox produces detailed execution logs and structured outcome reports, enabling reproducible comparisons of agent architectures and fine-grained analysis of reliability, prompt robustness, token usage, and generalization across tasks.


## Project Structure

```
/
├── agent/                                    # Agent implementations
│   ├── interfaces/                           # Agent interfaces
│   │   ├── core_agent_interface.py          # Core agent contract
│   │   └── fhir_agent_interface.py          # FHIR-specific interface
│   ├── fhir_baseline.py                     # Baseline ReAct agent
│   ├── fhir_plan_execute_agent.py           # Plan-and-Execute v1
│   └── fhir_plan_execute_agent_v2.py        # Plan-and-Execute v2 (OpenAI Tools)
│
├── tasks/                                   # The core benchmark modules.
│   └── fhir_tasks_modular/                  # Modular task implementations
│       ├── task_interface_modular.py        # Base task interface
│       ├── task_01_enter_new_patient_modular.py
│       ├── task_02a_search_existing_patient_modular.py
│       └── ... (43 task files)
│
├── environment/                             
│   ├── hapi-fhir/                           # FHIR server setup
│   │   ├── docker-compose.yml               # HAPI FHIR server config
│   ├── mcp/                                 # MCP servers
│   │   ├── baseline_server/                
│   │   │   ├── fhir_mcp_server.py          # Main FHIR MCP server
│   │   │   └── fhir_rest_server.py         # REST version of the FHIR server
│   │   └── memory_servers/                 
│   │       ├── fhir_memory_mcp_server.py   # Reflexion memory retrieval
│   │       ├── fhir_ref_mcp_server.py      # FHIR specs reference
│   │       └── memory_stores/              
│   ├── data/                                # Configuration & reference data
│   │   ├── fhir_res_ref_all/               # FHIR resource specs (JSON)
│   │   ├── fhir_datatypes_ref/             # FHIR datatype specs (JSON)
│   │   └── exp_*_task_variation*.yaml      # Task variation configs
│   └── indexes/                            
│       └── reflexion_faiss/                 # Reflexion memory indices
│
├── experiments/                              # Experiment runners
│   ├── run_experiment_fhir.py               # LangChain agents harness (5 configs)
│   ├── run_experiment_fhir_claude_code.py   # Claude Code harness (1 config)
│   ├── claude_code_configs/                 # MCP configs passed to `claude -p`
│   ├── verify_modular_tasks.py              # Task verification script
│   ├── start_servers.sh                     # Helper to start MCP servers
│   └── README.md                            # Experiment documentation

├── remote-deployment-bundle/                # Self-contained subset to copy to a VPS
│   └── README.md                            # Bundle setup instructions
│
├── training/                                 # Learning & optimization
│   └── fhir_reflexion_workflow.py           # Reflexion-based learning
│
├── prompts/                                 # System prompts
│   ├── fhir/                                # FHIR agent prompts
│   │   ├── fhir_baseline_system_prompt_with_refs.txt
│   │   ├── fhir_baseline_system_prompt_with_mem.txt
│   │   ├── fhir_planner_default_system_prompt.txt
│   │   ├── fhir_planner_system_prompt_with_mem.txt
│   │   └── fhir_planner_system_prompt_no_mem.txt
│   ├── reflexion_prompts/                   # Reflexion system prompts
│   │   ├── evaluator_system.txt
│   │   ├── reflector_system.txt
│   │   └── reflector_spec_system.txt
│   └── soft_validator_system_prompt.txt     # Soft validator prompt
│
├── utils/                                   # Shared utilities
│   ├── callbacks.py                         # LangChain callbacks (token tracking, tool recording)
│   ├── task_loader.py                       # Dynamic task loading
│   ├── soft_validator.py                    # LLM-based result validation
│   ├── fhir_formatting_helpers.py           # Formatting helpers
│   ├── tool_providers.py                    # MCP tool provider
│   ├── prompt_paraphraser.py                # Prompt paraphraser tool based on gpt-4.1
│   └── task_difficulty.py                   
│
├── analysis/                                # Analysis & visualization
│   └── soft_validator_analysis.ipynb        # Soft validation analysis
│
├── results/                                 # Execution logs (gitignored)
│   └── exp_*/                               # Per-experiment results
│
├── requirements.txt                          # Python dependencies
└── .gitignore                                # Git ignore rules
```

## Quick Start

### Prerequisites

- Python 3.10+
- Docker & Docker Compose (for FHIR server)
- OpenAI API key (or other LLM provider)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/YoussefMkst/FHIR-AgentEval.git
   cd FHIR-AgentEval
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   cp environment/.env.example environment/.env
   # Edit .env with your API keys and configurations
   ```

4. **Start the FHIR server**
   ```bash
   cd environment/hapi-fhir
   docker-compose up -d
   ```

5. **Start the MCP servers**

   `run_experiment_fhir.py` expects four MCP servers running on ports 8000,
   8010, 8011, and 8012. The helper script starts all four in the foreground
   with color-coded logs:

   ```bash
   ./experiments/start_servers.sh   # Ctrl+C stops all
   ```

   To start them individually instead, see `experiments/README.md`.

### Running Agents

**Baseline agent (standalone)**:
```bash
python agent/fhir_baseline.py --variations-yaml exp_1_task_variation_updated.yaml
```

**Full experiment with multiple agents**:
```bash
python experiments/run_experiment_fhir.py \
  --output-dir results/my_experiment \
  --variations-yaml environment/data/exp_1_task_variation_updated.yaml \
  --paraphrase
```

**Reflexion training loop**:
```bash
python training/fhir_reflexion_workflow.py \
  --yaml environment/data/exp_1_task_variation_updated.yaml \
  --use-specs
```

### Running with Claude Code

`experiments/run_experiment_fhir_claude_code.py` runs the benchmark through the
Claude Code CLI (`claude -p`) instead of the LangChain agents. Claude Code is
given the FHIR MCP server plus its default toolset (Bash, Read, Edit, Write,
Grep, etc.).

You can run it in two modes.

**Remote mode (recommended).** Claude Code runs on a VPS that also hosts the
HAPI server and the MCP servers. The harness on your laptop drives it over
SSH. Use the `remote-deployment-bundle/` folder to set the VPS up — see
`remote-deployment-bundle/README.md`.

```bash
# Point the harness at the VPS's HAPI for setup/validation:
echo "FHIR_SERVER_URL=http://<host-ip>:7070/fhir" >> environment/.env

python experiments/run_experiment_fhir_claude_code.py \
  --variations-yaml environment/data/exp_1_task_variation_updated.yaml \
  --ssh-target user@host \
  --model sonnet \
  --output-dir results/exp_claude_code
```

**Local mode (smoke tests only).** Omit `--ssh-target`. Claude Code runs on
your laptop, so HAPI and the MCP servers must run there too — deploy
`remote-deployment-bundle/` locally and start it the same way.

```bash
python experiments/run_experiment_fhir_claude_code.py \
  --variations-yaml environment/data/exp_1_task_variation_updated.yaml \
  --model sonnet \
  --output-dir results/exp_claude_code_local
```

Both example commands run the full variation set three times. `--output-dir`
is treated as a base name: results land in `<output-dir>_run_1`,
`<output-dir>_run_2`, and `<output-dir>_run_3`.

> **Warning — local mode may break the benchmark.** Claude Code's default toolset
> includes `Bash`, `Read`, and `Grep`, so when it runs on your laptop it can
> open the task source files in `tasks/`, the answer keys in the variation
> YAMLs, and the validator code. Use local mode only for quick checks; never
> use it for results you intend to report.
