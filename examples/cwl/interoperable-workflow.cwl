{
  "cwlVersion": "v1.2",
  "class": "Workflow",
  "label": "DAGonStar CWL interoperability",
  "inputs": {},
  "outputs": {
    "run_simulation_completed": {
      "type": "boolean",
      "outputSource": "run_simulation/completed"
    }
  },
  "steps": {
    "collect_observations": {
      "label": "collect-observations",
      "in": {},
      "out": [
        "completed"
      ],
      "run": {
        "class": "CommandLineTool",
        "label": "collect-observations",
        "requirements": {
          "InlineJavascriptRequirement": {}
        },
        "baseCommand": [
          "/bin/sh",
          "-c",
          "printf 'observations ready\\n'"
        ],
        "inputs": {},
        "outputs": {
          "completed": {
            "type": "boolean",
            "outputBinding": {
              "outputEval": "$(runtime.exitCode === 0)"
            }
          }
        }
      }
    },
    "prepare_parameters": {
      "label": "prepare-parameters",
      "in": {},
      "out": [
        "completed"
      ],
      "run": {
        "class": "CommandLineTool",
        "label": "prepare-parameters",
        "requirements": {
          "InlineJavascriptRequirement": {}
        },
        "baseCommand": [
          "/bin/sh",
          "-c",
          "printf 'parameters ready\\n'"
        ],
        "inputs": {},
        "outputs": {
          "completed": {
            "type": "boolean",
            "outputBinding": {
              "outputEval": "$(runtime.exitCode === 0)"
            }
          }
        }
      }
    },
    "run_simulation": {
      "label": "run-simulation",
      "in": {
        "after_collect_observations": "collect_observations/completed",
        "after_prepare_parameters": "prepare_parameters/completed"
      },
      "out": [
        "completed"
      ],
      "run": {
        "class": "CommandLineTool",
        "label": "run-simulation",
        "requirements": {
          "InlineJavascriptRequirement": {}
        },
        "baseCommand": [
          "/bin/sh",
          "-c",
          "printf 'simulation complete\\n'"
        ],
        "inputs": {
          "after_collect_observations": "boolean",
          "after_prepare_parameters": "boolean"
        },
        "outputs": {
          "completed": {
            "type": "boolean",
            "outputBinding": {
              "outputEval": "$(runtime.exitCode === 0)"
            }
          }
        }
      }
    }
  }
}
