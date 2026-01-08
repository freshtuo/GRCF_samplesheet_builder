#!/usr/bin/env bash
set -euo pipefail

mkdir -p tests/data tests/out

# Lane 1: dual-only; identical i7 is OK if i5 differs by >=3 (mismatches should stay 1)
# Lane 2: dual-only; too similar as a pair (effective distance=2) -> WARN + mismatches=0
# Lane 3: mixed; single-index i7 equals dual i7 -> ERROR
# Lane 4: mixed; single i7 close to dual i7 (dist=2) -> WARN + mismatches=0
cat > tests/data/input_min.csv << 'EOF'
lane,sample_id,project_id,i7_id,i5_id,i7,i5
"1,5,6",L1_S1,ILAB001,D701,D501,,
1,L1_S2,ILAB001,D701,D502,,
2,L2_S1,ILAB002,D701,D501,,
2,L2_S2,ILAB002,D703,D501,,
3,L3_DUAL,ILAB003,D701,D501,,
4,L4_DUAL,ILAB004,D701,D501,,
4,L4_SINGLE_WARN,ILAB004,D703,,,
EOF
#3,L3_SINGLE_BAD,ILAB003,D701,,,

# i7 table: include a sequence at Hamming distance 2 from D701
cat > tests/data/i7_illumina.csv << 'EOF'
Index_ID,Index_Seq
D701,ATTACTCG
D703,ATTACTAA
EOF

# i5 table: include two very different sequences so lane1 passes with mismatches=1
cat > tests/data/i5_illumina.csv << 'EOF'
Index_ID,Index_Seq
D501,TATAGCCT
D502,GGGGGGGG
EOF

# paired table optional (kept for compatibility with CLI, but not used in this test)
cat > tests/data/tenx_TT_setA.csv << 'EOF'
Index_ID,Index_I7,Index_I5
SI-TT-A1,TTTTTTTT,AAAAAAAA
EOF

echo "Wrote test files under tests/data/"

