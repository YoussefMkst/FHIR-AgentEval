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
│   ├── run_experiment_fhir.py               # Main experiment harness
│   ├── verify_modular_tasks.py              # Task verification script
│   ├── start_servers.sh                     # Helper to start MCP servers
│   └── README.md                            # Experiment documentation
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

5. **Start MCP servers** (from project root, in separate terminals)
   ```bash
   # FHIR operations server
   python environment/mcp/baseline_server/fhir_mcp_server.py --port 8000

   # FHIR reference server (for specs)
   python environment/mcp/memory_servers/fhir_ref_mcp_server.py --port 8010
   ```

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
