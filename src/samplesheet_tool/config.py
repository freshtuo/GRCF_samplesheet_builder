# config.py
# defaults & thresholds
#  

# characters allowed in sample id
SAMPLE_ID_ALLOWED = r"^[A-Za-z0-9._-]+$"

# default index mismatches
DEFAULT_BARCODE_MISMATCHES = 1

# index similarity thresholds (per lane, pairwise)
HAMMING_ERROR_DUPLICATE = 0   # identical index pair is handled as error separately
HAMMING_WARN_TIGHTEN = 1      # tighten mismatches to 0
HAMMING_WARN = 2              # warning only, mismatches to 0
HAMMING_OK_MIN = 3            # ok, mismatches to 1

# internal column names
COL_LANE = "lane"
COL_SAMPLE_ID = "sample_id"
COL_PROJECT_ID = "project_id"    # - iLab request ID
COL_I7_ID = "i7_id"              # - index i7 IDs
COL_I5_ID = "i5_id"              # - index i5 IDs
COL_I7 = "i7"                    # - index i7 sequences
COL_I5 = "i5"                    # - index i5 sequences
COL_LIBRARY_TYPE = "library_type"
COL_BARCODE_MISMATCHES = "barcode_mismatches"

# required columns
REQUIRED_CANONICAL_COLS = {COL_LANE, COL_SAMPLE_ID, COL_PROJECT_ID, COL_I7, COL_I5, COL_I7_ID, COL_I5_ID}

# lane range
LANE_RANGE = set(str(i) for i in range(1, 9))

