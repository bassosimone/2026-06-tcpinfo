#doc:
#doc: usage: make [target] [START=YYYY-MM-DD] [END=YYYY-MM-DD]
#doc:
#doc: START (included) and END (excluded) bound the data window and
#doc: default to the v2 window: 2026-01-01 to 2026-08-01, that is,
#doc: January through July 2026. Override them on the command line for
#doc: partial re-runs, e.g. resuming a failed export from a given week
#doc: onward.
#doc:
#doc: Example: make generate_queries START=2026-01-01 END=2026-02-01
#doc:
#doc: Targets:
#doc:
#doc: - help: print this help screen and exit
.PHONY: help
help:
	@cat GNUmakefile | grep '^#doc' | sed -e 's/^#doc: //g' -e 's/^#doc://g'

# Data window: START included; END excluded.
START = 2026-01-01
END = 2026-08-01

# SUFFIX mirrors the YYYYMMDD_YYYYMMDD file naming used by the scripts.
SUFFIX = $(subst -,,$(START))_$(subst -,,$(END))

# Chunk lists as "START:END" tokens. Weekly chunks clip at calendar
# month boundaries (see `scripts/list_chunks.py`). Recursively expanded
# using `=` on purpose: we only want to evaluate these two variables
# when they are actually used rather than on GNUmakefile parsing.
WEEKS = $(shell ./scripts/list_chunks.py --start-date $(START) --end-date $(END))
MONTHS = $(shell ./scripts/list_chunks.py --start-date $(START) --end-date $(END) --step month)

#doc:
#doc: - generate_queries: generates the SQL queries
.PHONY: generate_queries
generate_queries:
	@for c in $(WEEKS); do \
		./scripts/generate_queries.py --start-date $${c%:*} --end-date $${c#*:} \
			--template ndt7 --template tcpinfo || exit 1; \
	done
	@for c in $(MONTHS); do \
		./scripts/generate_queries.py --start-date $${c%:*} --end-date $${c#*:} \
			--template superset || exit 1; \
	done

#doc:
#doc: - export_mlab_data: exports M-Lab data via bq CLI
.PHONY: export_mlab_data
export_mlab_data: generate_queries
	@for c in $(WEEKS); do \
		./scripts/export_mlab_data.py --start-date $${c%:*} --end-date $${c#*:} || exit 1; \
	done

#doc:
#doc: - build_ndt7_download: builds ndt7 download parquet files
.PHONY: build_ndt7_download
build_ndt7_download:
	@for c in $(WEEKS); do \
		./scripts/build_ndt7_download.py --start-date $${c%:*} --end-date $${c#*:} || exit 1; \
	done

#doc:
#doc: - build_tcpinfo_download: builds tcpinfo download parquet files
.PHONY: build_tcpinfo_download
build_tcpinfo_download:
	@for c in $(WEEKS); do \
		./scripts/build_tcpinfo_download.py --start-date $${c%:*} --end-date $${c#*:} || exit 1; \
	done

#doc:
#doc: - build_superset_download: builds superset download parquet files
.PHONY: build_superset_download
build_superset_download:
	@for c in $(MONTHS); do \
		./scripts/build_superset_download.py --start-date $${c%:*} --end-date $${c#*:} || exit 1; \
	done

#doc:
#doc: - build_three_tier: builds three-tier joined parquet file
.PHONY: build_three_tier
build_three_tier:
	./scripts/build_three_tier.py --start-date $(START) --end-date $(END)

#doc:
#doc: - gap_distribution: gap distribution analysis
.PHONY: gap_distribution
gap_distribution:
	./scripts/gap_distribution.py --input data/three_tier_$(SUFFIX).parquet

#doc:
#doc: - gap_regression: gap regression analysis
.PHONY: gap_regression
gap_regression:
	./scripts/gap_regression.py --input data/three_tier_$(SUFFIX).parquet

#doc:
#doc: - error_propagation: error propagation analysis
.PHONY: error_propagation
error_propagation:
	./scripts/error_propagation.py --input data/three_tier_$(SUFFIX).parquet

#doc:
#doc: - t3_only_regression: T3-only gap regression analysis
.PHONY: t3_only_regression
t3_only_regression:
	./scripts/t3_only_regression.py --input data/three_tier_$(SUFFIX).parquet

#doc:
#doc: - tail_loss: Superset tail loss analysis
.PHONY: tail_loss
tail_loss:
	./scripts/tail_loss.py --input data/three_tier_$(SUFFIX).parquet

#doc:
#doc: - explorer: launch the TCPInfo measurement explorer (Streamlit)
.PHONY: explorer
explorer:
	uv run streamlit run explorer/app.py -- --file data/three_tier_$(SUFFIX).parquet

#doc:
