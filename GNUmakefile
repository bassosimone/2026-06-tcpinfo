#doc:
#doc: usage: make [target]
#doc:
#doc: Targets:
#doc:
#doc: - help: print this help screen and exit
.PHONY: help
help:
	@cat GNUmakefile | grep '^#doc' | sed -e 's/^#doc: //g' -e 's/^#doc://g'

#doc:
#doc: - generate_queries: generates the SQL queries
.PHONY: generate_queries
generate_queries:
	./scripts/generate_queries.py --start-date 2026-05-01 --end-date 2026-05-08 --template ndt7 --template tcpinfo
	./scripts/generate_queries.py --start-date 2026-05-08 --end-date 2026-05-15 --template ndt7 --template tcpinfo
	./scripts/generate_queries.py --start-date 2026-05-15 --end-date 2026-05-22 --template ndt7 --template tcpinfo
	./scripts/generate_queries.py --start-date 2026-05-22 --end-date 2026-05-29 --template ndt7 --template tcpinfo
	./scripts/generate_queries.py --start-date 2026-05-29 --end-date 2026-06-01 --template ndt7 --template tcpinfo
	./scripts/generate_queries.py --start-date 2026-05-01 --end-date 2026-06-01 --template superset

#doc:
#doc: - export_mlab_data: exports M-Lab data via bq CLI
.PHONY: export_mlab_data
export_mlab_data: generate_queries
	./scripts/export_mlab_data.py --start-date 2026-05-01 --end-date 2026-05-08
	./scripts/export_mlab_data.py --start-date 2026-05-08 --end-date 2026-05-15
	./scripts/export_mlab_data.py --start-date 2026-05-15 --end-date 2026-05-22
	./scripts/export_mlab_data.py --start-date 2026-05-22 --end-date 2026-05-29
	./scripts/export_mlab_data.py --start-date 2026-05-29 --end-date 2026-06-01

#doc:
#doc: - build_ndt7_download: builds ndt7 download parquet files
.PHONY: build_ndt7_download
build_ndt7_download:
	./scripts/build_ndt7_download.py --start-date 2026-05-01 --end-date 2026-05-08
	./scripts/build_ndt7_download.py --start-date 2026-05-08 --end-date 2026-05-15
	./scripts/build_ndt7_download.py --start-date 2026-05-15 --end-date 2026-05-22
	./scripts/build_ndt7_download.py --start-date 2026-05-22 --end-date 2026-05-29
	./scripts/build_ndt7_download.py --start-date 2026-05-29 --end-date 2026-06-01

#doc:
#doc: - build_tcpinfo_download: builds tcpinfo download parquet files
.PHONY: build_tcpinfo_download
build_tcpinfo_download:
	./scripts/build_tcpinfo_download.py --start-date 2026-05-01 --end-date 2026-05-08
	./scripts/build_tcpinfo_download.py --start-date 2026-05-08 --end-date 2026-05-15
	./scripts/build_tcpinfo_download.py --start-date 2026-05-15 --end-date 2026-05-22
	./scripts/build_tcpinfo_download.py --start-date 2026-05-22 --end-date 2026-05-29
	./scripts/build_tcpinfo_download.py --start-date 2026-05-29 --end-date 2026-06-01

#doc:
#doc: - build_superset_download: builds superset download parquet file
.PHONY: build_superset_download
build_superset_download:
	./scripts/build_superset_download.py --start-date 2026-05-01 --end-date 2026-06-01

#doc:
#doc: - build_three_tier: builds three-tier joined parquet file
.PHONY: build_three_tier
build_three_tier:
	./scripts/build_three_tier.py --start-date 2026-05-01 --end-date 2026-06-01

#doc:
#doc: - gap_distribution: gap distribution analysis
.PHONY: gap_distribution
gap_distribution:
	./scripts/gap_distribution.py --input data/three_tier_20260501_20260601.parquet

#doc:
#doc: - gap_regression: gap regression analysis
.PHONY: gap_regression
gap_regression:
	./scripts/gap_regression.py --input data/three_tier_20260501_20260601.parquet

#doc:
#doc: - error_propagation: error propagation analysis
.PHONY: error_propagation
error_propagation:
	./scripts/error_propagation.py --input data/three_tier_20260501_20260601.parquet

#doc:
#doc: - t3_only_regression: T3-only gap regression analysis
.PHONY: t3_only_regression
t3_only_regression:
	./scripts/t3_only_regression.py --input data/three_tier_20260501_20260601.parquet

#doc:
