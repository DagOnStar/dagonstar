#!/usr/bin/env cwl-runner
# Unmodified CWL workflow, run by StreamFlow or any CWL runner.
cwlVersion: v1.2
class: Workflow
inputs:
  text: File
  top:
    type: int
    default: 10
outputs:
  counts:
    type: File
    outputSource: count/counts
steps:
  count:
    in:
      text: text
      top: top
    out: [counts]
    run:
      class: CommandLineTool
      baseCommand: [sh, -c]
      arguments:
        - tr -s '[:space:]' '\n' < "$(inputs.text.path)" | tr '[:upper:]' '[:lower:]' | grep -v '^$' | sort | uniq -c | sort -k1,1nr -k2,2 | head -n $(inputs.top) | awk '{ printf "%s\t%s\n", $2, $1 }' > counts.tsv
      requirements:
        InlineJavascriptRequirement: {}
      inputs:
        text: File
        top: int
      outputs:
        counts:
          type: File
          outputBinding:
            glob: counts.tsv
