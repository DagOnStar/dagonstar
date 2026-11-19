// Unmodified Nextflow pipeline: counts words in params.text.
// DAGonStar passes the staged input through -params-file; no DAGonStar code here.
params.text = null
params.top = 10

process COUNT_WORDS {
    publishDir "results", mode: 'copy'

    input:
    path text

    output:
    path 'counts.tsv'

    script:
    """
    tr -s '[:space:]' '\\n' < ${text} | tr '[:upper:]' '[:lower:]' | grep -v '^\$' \\
      | sort | uniq -c | sort -k1,1nr -k2,2 | head -n ${params.top} \\
      | awk '{ printf "%s\\t%s\\n", \$2, \$1 }' > counts.tsv
    """
}

workflow {
    COUNT_WORDS(file(params.text, checkIfExists: true))
}
