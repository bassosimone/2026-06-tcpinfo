"""TCPInfo measurement explorer.

Streamlit app with two views:

- List: all tests from the three-tier parquet, with country
  and speed filters.
- Detail: select a test to see its tcp-info time series
  (RTT, speed, BBR phase, send buffer, stalls, bytes).

Run with: uv run streamlit run explorer/app.py -- --file data/three_tier.parquet
"""

import argparse
import glob
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

DESC_DIR = Path(__file__).resolve().parent

# Click's @click.command() decorator owns the process lifecycle (sys.exit on
# error, expects to be the entry point), which conflicts with Streamlit
# re-executing the script top-level on every widget interaction.
parser = argparse.ArgumentParser(description="TCPInfo measurement explorer")
parser.add_argument("--file", required=True, help="Path to the three-tier parquet file")
args = parser.parse_args()

SUMMARY_PATH = Path(args.file)
if not SUMMARY_PATH.exists():
    st.error(f"File not found: {SUMMARY_PATH}")
    st.stop()

DATA_DIR = SUMMARY_PATH.parent


@st.cache_data
def load_summary():
    df = pd.read_parquet(SUMMARY_PATH)
    df["speed_mbps"] = (
        df["t2_tcp_BytesAcked"] * 8 / (df["t2_tcp_ElapsedTime"] / 1e6) / 1e6
    )
    df["minrtt_ms"] = df["t2_tcp_MinRTT"] / 1000
    return df


@st.cache_data
def load_snapshots(tier):
    # TODO(bassosimone): currently this filter matches (a) download
    # files and (b) tcp-info snapshots. Merging works because we are
    # filtering on UUID. We will need to improve this code later on
    # when we add support for loading upload data as well.
    pattern = str(DATA_DIR / f"{tier}_*.parquet")
    files = sorted(glob.glob(pattern))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def compute_elapsed(snaps, tier, start_time=None):
    if tier == "ndt7":
        return snaps["tcp_ElapsedTime"] / 1e6
    ts = pd.to_datetime(snaps["timestamp"], utc=True)
    if start_time is not None:
        origin = pd.Timestamp(start_time, tz="UTC")
        return (ts - origin).dt.total_seconds()
    return (ts - ts.min()).dt.total_seconds()


def _source_labels(mode):
    if mode == "Both":
        return "(sidecar)", "(server)"
    if mode == "Merged":
        return "(merged)", None
    if mode == "Server":
        return None, ""
    return "", None


def _add_both(fig, elapsed_t1, snaps_t1, elapsed_t2, snaps_t2, y_fn, name, mode, **kw):
    lbl_t1, lbl_t2 = _source_labels(mode)
    if elapsed_t1 is not None:
        suffix = f" {lbl_t1}" if lbl_t1 else ""
        fig.add_trace(
            go.Scatter(
                x=elapsed_t1,
                y=y_fn(snaps_t1),
                name=f"{name}{suffix}",
                mode="lines+markers",
                **kw,
            )
        )
    kw_server = dict(kw)
    kw_server["line"] = dict(kw.get("line", {}), dash="dash")
    if elapsed_t2 is not None:
        suffix = f" {lbl_t2}" if lbl_t2 else ""
        fig.add_trace(
            go.Scatter(
                x=elapsed_t2,
                y=y_fn(snaps_t2),
                name=f"{name}{suffix}",
                mode="lines+markers",
                **kw_server,
            )
        )


def chart_rtt(elapsed_t1, snaps_t1, elapsed_t2, snaps_t2, mode):
    fig = go.Figure()
    args = (elapsed_t1, snaps_t1, elapsed_t2, snaps_t2)
    _add_both(fig, *args, lambda s: s["tcp_RTT"] / 1000, "RTT", mode)
    _add_both(fig, *args, lambda s: s["tcp_MinRTT"] / 1000, "MinRTT", mode)
    _add_both(fig, *args, lambda s: s["tcp_RTTVar"] / 1000, "RTTVar", mode)
    _add_both(fig, *args, lambda s: s["bbr_MinRTT"] / 1000, "BBR MinRTT", mode)
    fig.update_layout(yaxis_title="ms", xaxis_title="elapsed (s)", height=400)
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=True)
    return fig


def chart_speed(
    elapsed_t1, snaps_t1, elapsed_t2, snaps_t2, mode, client_speed_mbps=None
):
    fig = go.Figure()
    lbl_t1, lbl_t2 = _source_labels(mode)
    for elapsed, snaps, label, dash in [
        (elapsed_t1, snaps_t1, lbl_t1, None),
        (elapsed_t2, snaps_t2, lbl_t2, "dash"),
    ]:
        if elapsed is None or label is None:
            continue
        suffix = f" {label}" if label else ""
        dt = elapsed - elapsed.iloc[0]
        avg_tput = snaps["tcp_BytesAcked"] * 8 / dt.where(dt > 0) / 1e6
        fig.add_trace(
            go.Scatter(
                x=elapsed,
                y=avg_tput,
                name=f"Avg Throughput{suffix}",
                mode="lines+markers",
                line={"dash": dash},
            )
        )
        fig.add_trace(
            go.Scatter(
                x=elapsed,
                y=snaps["bbr_BW"] * 8 / 1e6,
                name=f"BBR BW{suffix}",
                mode="lines+markers",
                line={"dash": dash},
            )
        )
        fig.add_trace(
            go.Scatter(
                x=elapsed,
                y=snaps["tcp_DeliveryRate"] * 8 / 1e6,
                name=f"Delivery Rate{suffix}",
                mode="lines+markers",
                line={"dash": dash},
            )
        )
        fig.add_trace(
            go.Scatter(
                x=elapsed,
                y=snaps["tcp_PacingRate"] * 8 / 1e6,
                name=f"Pacing Rate{suffix}",
                mode="lines+markers",
                line={"dash": dash},
            )
        )
    if client_speed_mbps is not None:
        fig.add_hline(
            y=client_speed_mbps,
            line_dash="dot",
            line_color="black",
            annotation_text=f"<b>Client-reported: {client_speed_mbps:.1f} Mbps</b>",
            annotation_position="top left",
            annotation_bgcolor="rgba(255,255,255,0.85)",
        )
    fig.update_layout(yaxis_title="Mbps", xaxis_title="elapsed (s)", height=400)
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=True)
    return fig


def chart_bbr_phase(elapsed_t1, snaps_t1, elapsed_t2, snaps_t2, mode):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    lbl_t1, lbl_t2 = _source_labels(mode)
    for elapsed, snaps, label, dash in [
        (elapsed_t1, snaps_t1, lbl_t1, None),
        (elapsed_t2, snaps_t2, lbl_t2, "dash"),
    ]:
        if elapsed is None or label is None:
            continue
        suffix = f" {label}" if label else ""
        fig.add_trace(
            go.Scatter(
                x=elapsed,
                y=snaps["bbr_PacingGain"] / 256,
                name=f"PacingGain{suffix}",
                mode="lines+markers",
                line={"dash": dash},
            ),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=elapsed,
                y=snaps["bbr_CwndGain"] / 256,
                name=f"CwndGain{suffix}",
                mode="lines+markers",
                line={"dash": dash},
            ),
            secondary_y=True,
        )
    fig.update_yaxes(
        title_text="PacingGain",
        tickvals=[0.34, 0.75, 1.00, 1.25, 2.89],
        ticktext=[
            "Drain (0.34)",
            "BW drain (0.75)",
            "BW cruise (1.00)",
            "BW probe (1.25)",
            "Startup (2.89)",
        ],
        showgrid=True,
        secondary_y=False,
    )
    fig.update_yaxes(
        title_text="CwndGain",
        tickvals=[1.00, 2.00, 2.89],
        ticktext=["ProbeRTT (1.00)", "ProbeBW (2.00)", "Startup (2.89)"],
        showgrid=False,
        secondary_y=True,
    )
    fig.update_layout(
        xaxis_title="elapsed (s)",
        height=400,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
        },
    )
    fig.update_xaxes(showgrid=True)
    return fig


def chart_bytes(elapsed_t1, snaps_t1, elapsed_t2, snaps_t2, mode):
    fig = go.Figure()
    args = (elapsed_t1, snaps_t1, elapsed_t2, snaps_t2)
    _add_both(
        fig, *args, lambda s: s["tcp_BytesAcked"] / (1024 * 1024), "BytesAcked", mode
    )
    fig.update_layout(yaxis_title="MB", xaxis_title="elapsed (s)", height=400)
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=True)
    return fig


def chart_castate(elapsed_t1, snaps_t1, elapsed_t2, snaps_t2, mode):
    fig = go.Figure()
    args = (elapsed_t1, snaps_t1, elapsed_t2, snaps_t2)
    _add_both(fig, *args, lambda s: s["tcp_CAState"], "CAState", mode)
    fig.update_layout(
        yaxis_title="state",
        xaxis_title="elapsed (s)",
        yaxis={
            "tickvals": [0, 1, 2, 3, 4],
            "ticktext": ["Open", "Disorder", "CWR", "Recovery", "Loss"],
        },
        height=400,
    )
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=True)
    return fig


def chart_notsent(elapsed_t1, snaps_t1, elapsed_t2, snaps_t2, mode):
    fig = go.Figure()
    args = (elapsed_t1, snaps_t1, elapsed_t2, snaps_t2)
    _add_both(fig, *args, lambda s: s["tcp_NotsentBytes"] / 1024, "NotsentBytes", mode)
    fig.update_layout(yaxis_title="KB", xaxis_title="elapsed (s)", height=400)
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=True)
    return fig


def chart_stalls(elapsed_t1, snaps_t1, elapsed_t2, snaps_t2, mode):
    fig = go.Figure()
    args = (elapsed_t1, snaps_t1, elapsed_t2, snaps_t2)
    _add_both(fig, *args, lambda s: s["tcp_BusyTime"] / 1000, "BusyTime", mode)
    _add_both(fig, *args, lambda s: s["tcp_RWndLimited"] / 1000, "RWndLimited", mode)
    _add_both(
        fig, *args, lambda s: s["tcp_SndBufLimited"] / 1000, "SndBufLimited", mode
    )
    fig.update_layout(
        yaxis_title="ms (cumulative)",
        xaxis_title="elapsed (s)",
        height=400,
    )
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=True)
    return fig


def chart_flight_size(elapsed_t1, snaps_t1, elapsed_t2, snaps_t2, mode):
    fig = go.Figure()
    lbl_t1, lbl_t2 = _source_labels(mode)
    for elapsed, snaps, label, dash in [
        (elapsed_t1, snaps_t1, lbl_t1, None),
        (elapsed_t2, snaps_t2, lbl_t2, "dash"),
    ]:
        if elapsed is None or label is None:
            continue
        suffix = f" {label}" if label else ""
        inflight = (
            (
                snaps["tcp_Unacked"]
                - snaps["tcp_Sacked"]
                - snaps["tcp_Lost"]
                + snaps["tcp_Retrans"]
            )
            * snaps["tcp_SndMSS"]
            / 1024
        )
        fig.add_trace(
            go.Scatter(
                x=elapsed,
                y=inflight,
                name=f"Kernel inflight{suffix}",
                mode="lines+markers",
                line={"dash": dash},
            )
        )
        fig.add_trace(
            go.Scatter(
                x=elapsed,
                y=snaps["tcp_SndCwnd"] * snaps["tcp_SndMSS"] / 1024,
                name=f"SndCwnd × MSS{suffix}",
                mode="lines+markers",
                line={"dash": dash},
            )
        )
        fig.add_trace(
            go.Scatter(
                x=elapsed,
                y=snaps["tcp_SndWnd"] / 1024,
                name=f"RWND{suffix}",
                mode="lines+markers",
                line={"dash": dash},
            )
        )
    fig.update_layout(yaxis_title="KB", xaxis_title="elapsed (s)", height=400)
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=True)
    return fig


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

st.set_page_config(page_title="TCPInfo Explorer", layout="wide")
st.title("TCPInfo Explorer")
st.markdown("""
Interactive explorer for ndt7 download measurements collected from
Giga-connected schools in Malawi and Madagascar (May 2026). Each test
is shown as a full TCPInfo/BBRInfo time series from two independent
data sources — the ndt7 server and the tcp-info sidecar — which can
be overlaid, viewed separately, or merged. Use the sidebar to filter
by country, speed, RTT, server, or school, then select a test to
inspect its TCP dynamics. For detailed variable definitions and
interpretive guidance, see
`docs/tcpinfo_inventory_llm.txt` in the repository.
""")

summary = load_summary()

st.sidebar.header("Controls")
source_mode = st.sidebar.radio(
    "Data source",
    ["Both", "Server", "Sidecar", "Merged"],
    index=0,
)

st.sidebar.header("Filters")

countries = ["All"] + sorted(summary["country_code"].dropna().unique().tolist())
country = st.sidebar.selectbox("Country", countries)

all_dates = sorted(summary["t2_date"].unique())
date_range = st.sidebar.select_slider(
    "Date range",
    options=all_dates,
    value=(all_dates[0], all_dates[-1]),
)

speed_max = float(summary["speed_mbps"].max())
speed_range = st.sidebar.slider(
    "Speed (Mbps)",
    0.0,
    speed_max,
    (0.0, speed_max),
    step=1.0,
)

rtt_cap = 1000.0
rtt_range = st.sidebar.slider(
    "MinRTT (ms)",
    0.0,
    rtt_cap,
    (0.0, rtt_cap),
    step=1.0,
)

servers = ["All"] + sorted(summary["t2_server_site"].dropna().unique().tolist())
server = st.sidebar.selectbox("Server site", servers)

schools = ["All"] + sorted(summary["school_id"].dropna().unique().tolist())
school = st.sidebar.selectbox("School", schools)

t1_snap_max = int(summary["t1_n_snapshots"].max())
t1_snap_range = st.sidebar.slider(
    "T1 snapshots (sidecar)",
    1,
    t1_snap_max,
    (1, t1_snap_max),
)

t2_samp_max = int(summary["t2_n_samples"].max())
t2_samp_range = st.sidebar.slider(
    "T2 samples (ndt7)",
    1,
    t2_samp_max,
    (1, t2_samp_max),
)

filtered = summary
if country != "All":
    filtered = filtered[filtered["country_code"] == country]
filtered = filtered[
    (filtered["t2_date"] >= date_range[0]) & (filtered["t2_date"] <= date_range[1])
]
filtered = filtered[
    (filtered["speed_mbps"] >= speed_range[0])
    & (filtered["speed_mbps"] <= speed_range[1])
]
filtered = filtered[
    (filtered["minrtt_ms"] >= rtt_range[0]) & (filtered["minrtt_ms"] <= rtt_range[1])
]
if server != "All":
    filtered = filtered[filtered["t2_server_site"] == server]
if school != "All":
    filtered = filtered[filtered["school_id"] == school]
filtered = filtered[
    (filtered["t1_n_snapshots"] >= t1_snap_range[0])
    & (filtered["t1_n_snapshots"] <= t1_snap_range[1])
]
filtered = filtered[
    (filtered["t2_n_samples"] >= t2_samp_range[0])
    & (filtered["t2_n_samples"] <= t2_samp_range[1])
]

st.divider()
st.subheader(f"Available Tests ({len(filtered):,})")
display_cols = [
    "uuid",
    "country_code",
    "t2_date",
    "t2_server_site",
    "speed_mbps",
    "minrtt_ms",
    "school_id",
    "t1_n_snapshots",
    "t2_n_samples",
]
display_df = filtered[display_cols].sort_values("t2_date").reset_index(drop=True)

if display_df.empty:
    st.warning("No tests match the filters.")
    st.stop()

if "selected_uuid" not in st.session_state:
    st.session_state.selected_uuid = None
if "prev_table_uuid" not in st.session_state:
    st.session_state.prev_table_uuid = None

event = st.dataframe(
    display_df,
    width="stretch",
    height=300,
    on_select="rerun",
    selection_mode="single-row",
)

if event.selection.rows:
    table_uuid = display_df.iloc[event.selection.rows[0]]["uuid"]
    if table_uuid != st.session_state.prev_table_uuid:
        st.session_state.selected_uuid = table_uuid
        st.session_state.prev_table_uuid = table_uuid

uuids = display_df["uuid"].tolist()
current = st.session_state.selected_uuid
default_idx = uuids.index(current) if current in uuids else 0

uuid_info = filtered.set_index("uuid")[
    ["speed_mbps", "minrtt_ms", "country_code", "t2_date"]
].to_dict("index")


def format_uuid(u):
    info = uuid_info.get(u, {})
    return (
        f"{u} — "
        f"{info.get('speed_mbps', 0):.1f} Mbps, "
        f"{info.get('minrtt_ms', 0):.0f} ms RTT, "
        f"{info.get('country_code', '?')}, "
        f"{info.get('t2_date', '?')}"
    )


selected = st.selectbox(
    "Or pick from list",
    uuids,
    index=default_idx,
    format_func=format_uuid,
)
st.session_state.selected_uuid = selected

all_snaps_t1 = load_snapshots("tcpinfo")
all_snaps_t2 = load_snapshots("ndt7")
snaps_t1 = all_snaps_t1[all_snaps_t1["uuid"] == selected].sort_values("snapshot_index")
snaps_t2 = all_snaps_t2[all_snaps_t2["uuid"] == selected].sort_values("snapshot_index")

if snaps_t1.empty and snaps_t2.empty:
    st.warning(f"No snapshots found for {selected}.")
    st.stop()

has_t1 = not snaps_t1.empty
has_t2 = not snaps_t2.empty
t2_start = snaps_t2["start_time"].iloc[0] if has_t2 else None
elapsed_t1_raw = (
    compute_elapsed(snaps_t1, "tcpinfo", start_time=t2_start) if has_t1 else None
)
elapsed_t2_raw = compute_elapsed(snaps_t2, "ndt7") if has_t2 else None

if source_mode == "Server":
    elapsed_t1, elapsed_t2 = None, elapsed_t2_raw
    snaps_t1_view = snaps_t1
elif source_mode == "Sidecar":
    elapsed_t1, elapsed_t2 = elapsed_t1_raw, None
    snaps_t1_view = snaps_t1
elif source_mode == "Merged":
    parts_e, parts_s = [], []
    if has_t1:
        parts_e.append(elapsed_t1_raw)
        parts_s.append(snaps_t1)
    if has_t2:
        parts_e.append(elapsed_t2_raw)
        parts_s.append(snaps_t2)
    if parts_e:
        merged_elapsed = pd.concat(parts_e, ignore_index=True)
        merged_snaps = pd.concat(parts_s, ignore_index=True)
        order = merged_elapsed.argsort()
        elapsed_t1 = merged_elapsed.iloc[order].reset_index(drop=True)
        snaps_t1_view = merged_snaps.iloc[order].reset_index(drop=True)
    else:
        elapsed_t1 = None
        snaps_t1_view = snaps_t1
    elapsed_t2 = None
else:
    elapsed_t1, elapsed_t2 = elapsed_t1_raw, elapsed_t2_raw
    snaps_t1_view = snaps_t1


st.divider()

st.subheader("Selected Test")
test_row = filtered[filtered["uuid"] == selected].iloc[0]
props_df = pd.DataFrame(
    {
        "Property": [
            "UUID",
            "Country",
            "Date",
            "Server",
            "Speed (Mbps)",
            "MinRTT (ms)",
            "School",
            "T1 Snapshots",
            "T2 Samples",
        ],
        "Value": [
            selected,
            test_row["country_code"],
            str(test_row["t2_date"]),
            test_row.get("t2_server_site", ""),
            f"{test_row['speed_mbps']:.1f}",
            f"{test_row['minrtt_ms']:.0f}",
            test_row.get("school_id", ""),
            str(int(test_row["t1_n_snapshots"])),
            str(int(test_row["t2_n_samples"])),
        ],
    }
)
st.dataframe(props_df, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

client_et = test_row.get("t3_client_elapsed_time")
client_nb = test_row.get("t3_client_num_bytes")
client_speed = None
if client_et and client_et > 0 and client_nb:
    client_speed = client_nb * 8 / client_et / 1e6

CHARTS = [
    ("Round-Trip Time", "rtt", chart_rtt, {}),
    ("Speed", "speed", chart_speed, {"client_speed_mbps": client_speed}),
    ("Cumulative Bytes", "bytes", chart_bytes, {}),
    ("BBR Phase", "bbr_phase", chart_bbr_phase, {}),
    ("Bytes in Flight", "flight_size", chart_flight_size, {}),
    ("Congestion Avoidance State", "castate", chart_castate, {}),
    ("Send Buffer", "notsent", chart_notsent, {}),
    ("Stalls", "stalls", chart_stalls, {}),
]

for title, key, fn, extra_kw in CHARTS:
    st.divider()
    st.subheader(title)
    desc_path = DESC_DIR / f"{key}.md"
    if desc_path.exists():
        with st.expander("About this chart"):
            st.markdown(desc_path.read_text())
    st.plotly_chart(
        fn(
            elapsed_t1,
            snaps_t1_view,
            elapsed_t2,
            snaps_t2,
            mode=source_mode,
            **extra_kw,
        ),
        width="stretch",
    )
