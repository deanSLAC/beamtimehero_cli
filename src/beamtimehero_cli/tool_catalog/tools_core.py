"""Core beamline tool handlers — wraps spec_cmd and data/log readers.

Each tool is exposed via tool_catalog.definitions. SPEC-mutating tools
delegate to `spec_cmd.call()`, which writes an action_log row before
dispatch. Read-only tools touch only the local filesystem.

Every SPEC-mutating tool requires a non-empty `justification` argument;
the dispatcher refuses to run without it.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import matplotlib
matplotlib.use("Agg")
import numpy as np

from beamtimehero_cli.action_log.db import recent_actions
from beamtimehero_cli.spec_control import phase_allowlist, spec_cmd
from beamtimehero_cli.spec_data import scans as scan_data
from beamtimehero_cli.spec_data import plotting
from beamtimehero_cli.spec_data.plotting import fig_to_base64
from beamtimehero_cli.spec_logs import log_reader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _as_json(result: dict | list | str) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)

def _refuse_rerun_if_already_done(command: str, human_name: str) -> Optional[str]:
    """Gate long-running macros so the agent can never trigger them
    twice. If the action_log already shows a successful run for the
    current experiment, return the refusal JSON string; otherwise
    return None and the caller should proceed.

    Why: these macros take minutes and physically re-align hardware.
    A phase-gate failure (e.g. a stale in-memory flag) used to make
    the agent 'helpfully' retry. Never again. The user can reset the
    run via the dashboard Reset button if they want to redo it.
    """
    try:
        from beamtimehero_cli.action_log.db import recent_actions
    except Exception:
        return None
    experiment_id = spec_cmd.get_experiment_id()
    if not experiment_id:
        return None
    try:
        actions = recent_actions(limit=100, experiment_id=experiment_id)
    except Exception:
        return None
    prior = next(
        (a for a in actions if a.get("command") == command and a.get("success") == 1),
        None,
    )
    if prior is None:
        return None
    return json.dumps({
        "ok": False,
        "already_done": True,
        "prior_action_id": prior.get("id"),
        "error": (
            f"{human_name} already succeeded for this experiment "
            f"(action {prior.get('id')}). This macro is one-shot — "
            "call transition_phase to move on. The operator can force "
            "a re-run via the dashboard Reset button."
        ),
    })

# ===========================================================================
# CAT-0 · High-level procedural macros
# ===========================================================================

def t_align_beamline(args: dict) -> tuple[str, list[str]]:
    refusal = _refuse_rerun_if_already_done("align_beamline", "align_beamline")
    if refusal is not None:
        return refusal, []
    justification = (args.get("justification") or "").strip()
    a = [
        str(args.get("energy", 0)),
        str(args.get("xtal_chg", 0)),
        str(args.get("fine_x", 0)),
        str(args.get("fine_z", 0)),
    ]
    res = spec_cmd.call("align_beamline", a, justification=justification)
    return _as_json(res), []

def t_align_xes(args: dict) -> tuple[str, list[str]]:
    refusal = _refuse_rerun_if_already_done("align_xes", "align_xes_spectrometer")
    if refusal is not None:
        return refusal, []
    j = (args.get("justification") or "").strip()
    crystals = str(args.get("crystals", "1234567"))
    a = [crystals, str(args.get("en_xes", 0)), str(args.get("en_mono", 0))]
    res = spec_cmd.call("align_xes", a, justification=j)
    return _as_json(res), []

def t_auto_sample_align(args: dict) -> tuple[str, list[str]]:
    refusal = _refuse_rerun_if_already_done("auto_sample_align", "auto_sample_align")
    if refusal is not None:
        return refusal, []
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("auto_sample_align", [], justification=j)
    return _as_json(res), []

def t_run_collection(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("run_collection", [], justification=j)
    return _as_json(res), []

def t_select_element(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("select_element", [str(args["element"])], justification=j)
    return _as_json(res), []

def t_peak_mono_pitch(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("peak_mono_pitch", [], justification=j)
    return _as_json(res), []

def t_calibrate_mono(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("calibrate_mono", [str(args["tabulated_edge_ev"])], justification=j)
    return _as_json(res), []

# ===========================================================================
# CAT-1 · Motor control
# ===========================================================================

def t_move_motor(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("umv", [str(args["motor"]), str(args["position"])], justification=j)
    return _as_json(res), []

def t_move_motor_relative(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("umvr", [str(args["motor"]), str(args["delta"])], justification=j)
    return _as_json(res), []

def t_read_motor_position(args: dict) -> tuple[str, list[str]]:
    res = spec_cmd.call("p_motor", [str(args["motor"])], justification="")
    return _as_json(res), []

def t_wa(args: dict) -> tuple[str, list[str]]:
    res = spec_cmd.call("wa", [], justification="")
    return _as_json(res), []

# ===========================================================================
# CAT-2 · Scan execution
# ===========================================================================

def t_run_motor_scan(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    a = [
        str(args["motor"]),
        str(args["start"]),
        str(args["end"]),
        str(args["npoints"]),
        str(args["count_time"]),
    ]
    res = spec_cmd.call("ascan", a, justification=j)
    return _as_json(res), []

def t_run_motor_scan_relative(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    a = [
        str(args["motor"]),
        str(args["delta_start"]),
        str(args["delta_end"]),
        str(args["npoints"]),
        str(args["count_time"]),
    ]
    res = spec_cmd.call("dscan", a, justification=j)
    return _as_json(res), []

def t_run_diagonal_scan(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    motor1 = str(args["motor1"])
    motor2 = str(args["motor2"])
    # Pre-validate motor2: the dispatcher's motor allow-check only sees
    # args[motor_arg_index=0] (motor1). motor2 lives at args[3] in the
    # rendered list, so we have to gate it here.
    phase = spec_cmd.get_phase()
    if phase != phase_allowlist.PHASE_UNRESTRICTED and \
            not phase_allowlist.motor_allowed(phase, motor2):
        return json.dumps({
            "ok": False,
            "error": f"motor '{motor2}' not on allowlist for phase '{phase}'",
        }), []
    delta = args.get("delta")
    delta_lo_explicit = "delta_lo" in args
    delta_hi_explicit = "delta_hi" in args
    if delta is not None and (delta_lo_explicit or delta_hi_explicit):
        return json.dumps({
            "ok": False,
            "error": "pass either `delta` (symmetric) or `delta_lo`+`delta_hi`, not both",
        }), []
    if delta is not None:
        delta_lo = -float(delta)
        delta_hi = +float(delta)
    else:
        delta_lo = args.get("delta_lo", -8)
        delta_hi = args.get("delta_hi", 8)
    a = [
        motor1, str(delta_lo), str(delta_hi),
        motor2, str(delta_lo), str(delta_hi),
        str(args["npoints"]), str(args["count_time"]),
    ]
    res = spec_cmd.call("d2scan", a, justification=j)
    return _as_json(res), []

def t_fit_emission_peak(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    a: list[str] = []
    sn = args.get("scan_number")
    if sn is not None:
        a.append(str(int(sn)))
    res = spec_cmd.call("get_HERFD_energy", a, justification=j)
    return _as_json(res), []

def t_run_xas(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    element = args.get("element")
    if element:
        sel_res = spec_cmd.call("select_element", [str(element)], justification=j)
        if not sel_res.get("ok", True):
            return _as_json(sel_res), []
    cnt_sec = args.get("count_time")
    nbr_scan = args.get("n_reps")
    emission = args.get("emission_ev")
    nbr_filter = args.get("filter")
    a = [
        str(1.0 if cnt_sec is None else cnt_sec),
        str(1 if nbr_scan is None else nbr_scan),
        str(0 if emission is None else emission),
        str(-1 if nbr_filter is None else nbr_filter),
    ]
    res = spec_cmd.call("run_xas", a, justification=j)
    return _as_json(res), []

def t_run_emiss_scan(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    a = [
        str(args["element"]),
        str(args["count_time"]),
        str(args["n_reps"]),
        str(args["emission_ev"]),
        str(args.get("filter", 0)),
    ]
    res = spec_cmd.call("emiss_scan", a, justification=j)
    return _as_json(res), []

# ===========================================================================
# CAT-3 · Beamline configuration
# ===========================================================================

def t_mv_energy(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("mv_energy", [str(args["energy_ev"])], justification=j)
    return _as_json(res), []

def t_shutter(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    a = [str(args["command"])]
    if "delay_s" in args:
        a.append(str(args["delay_s"]))
    res = spec_cmd.call("shutter", a, justification=j)
    return _as_json(res), []

def t_set_filter(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("mv", ["filter", str(args["bitmask"])], justification=j)
    return _as_json(res), []

def t_safely_remove_filters(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("safely_remove_filters", [], justification=j)
    return _as_json(res), []

def t_set_gain(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    which = args["which"]
    cmd = {"i0": "set_i0_gain", "i1": "set_i1_gain", "i2": "set_i2_gain"}.get(which)
    if not cmd:
        return json.dumps({"ok": False, "error": f"invalid gain channel: {which}"}), []
    res = spec_cmd.call(cmd, [str(args["gain_setting"])], justification=j)
    return _as_json(res), []

def t_set_vortex_roi(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    mode = args.get("mode", "auto")
    if mode == "auto":
        a = ["auto", str(args.get("channel", 1))]
    else:
        a = [str(args["channel"]), str(args["lo_ev"]), str(args["hi_ev"])]
    res = spec_cmd.call("set_vortex_roi", a, justification=j)
    return _as_json(res), []

def t_open_data_file(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("newfile", [str(args["filename"])], justification=j)
    return _as_json(res), []

def t_plotselect(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("plotselect", [str(args["counter"])], justification=j)
    return _as_json(res), []

# ===========================================================================
# CAT-4 · Alignment fallbacks
# ===========================================================================

def t_run_align_shortcut(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    name = args["name"]
    allowed = {
        "vvv", "hhh", "m1m1", "m2m2", "ggg", "bzbz", "bxbx",
        "dmm", "beamx", "beamz", "cm1m1", "cm2m2", "beamx_fine", "beamz_fine",
    }
    if name not in allowed:
        return json.dumps({"ok": False, "error": f"shortcut '{name}' not allowed"}), []
    res = spec_cmd.call("run_shortcut", [name], justification=j)
    return _as_json(res), []

def t_post_scan_move(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    mode = args["mode"]
    if mode not in ("cen", "peak"):
        return json.dumps({"ok": False, "error": "mode must be 'cen' or 'peak'"}), []
    res = spec_cmd.call(mode, [], justification=j)
    return _as_json(res), []

# ===========================================================================
# CAT-5 · Beam-diagnostic tool (sample-position diagnostic, alignment)
# ===========================================================================

def t_mv_pinhole(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("mvpinhole", [], justification=j)
    return _as_json(res), []

def t_mv_plastic(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("mvplastic", [], justification=j)
    return _as_json(res), []

def t_mv_knife_clear(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("mvknifeclear", [], justification=j)
    return _as_json(res), []

def t_mv_knife_out(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("mvknifewayout", [], justification=j)
    return _as_json(res), []

def t_measure_beam_size(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    mode_x = "1" if bool(args.get("small_x", False)) else "0"
    mode_z = "1" if bool(args.get("small_z", False)) else "0"
    res = spec_cmd.call("measure_beam_size", [mode_x, mode_z], justification=j)
    return _as_json(res), []

def t_zero_pinhole(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("zero_pinhole", [], justification=j)
    return _as_json(res), []

def t_small_beam(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("smallbeam", [], justification=j)
    return _as_json(res), []

def t_big_beam(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("bigbeam", [], justification=j)
    return _as_json(res), []

def t_xtal_align(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("xtalalign", [], justification=j)
    return _as_json(res), []

def t_reset_gap(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("reset_gap", [], justification=j)
    return _as_json(res), []

def t_set_m2_stripe(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    if "energy_ev" not in args:
        return json.dumps({"ok": False, "error": "'energy_ev' (number) is required"}), []
    res = spec_cmd.call("m2_stripe", [str(args["energy_ev"])], justification=j)
    return _as_json(res), []

def t_get_anchor(args: dict) -> tuple[str, list[str]]:
    res = spec_cmd.call("get_anchor", [], justification="")
    return _as_json(res), []

def t_set_anchor(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("set_anchor", [], justification=j)
    return _as_json(res), []

def t_tracking(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    if "enabled" not in args:
        return json.dumps({"ok": False, "error": "'enabled' (boolean) is required"}), []
    flag = "1" if bool(args["enabled"]) else "0"
    res = spec_cmd.call("tracking", [flag], justification=j)
    return _as_json(res), []

# ===========================================================================
# CAT-6 · Beam monitoring
# ===========================================================================

def t_get_beam_size(args: dict) -> tuple[str, list[str]]:
    res = spec_cmd.call("wbeamsize", [], justification="")
    return _as_json(res), []

def t_get_beam_status(args: dict) -> tuple[str, list[str]]:
    res = spec_cmd.call("beam_status", [], justification="")
    return _as_json(res), []

def t_get_counts(args: dict) -> tuple[str, list[str]]:
    t = args.get("count_time", 1)
    res = spec_cmd.call("ct", [str(t)], justification="")
    return _as_json(res), []

def t_get_counter(args: dict) -> tuple[str, list[str]]:
    t = args.get("count_time", 1)
    res = spec_cmd.call("ct", [str(t)], justification="")
    if res.get("ok") and "counters" in res.get("result", {}):
        name = args["counter"]
        counters = res["result"]["counters"]
        if name in counters:
            res["result"] = {"value": counters[name], "counter": name, "raw": res["result"].get("raw", "")}
        else:
            available = list(counters.keys())
            res = {"ok": False, "error": f"Counter '{name}' not found. Available: {available}"}
    return _as_json(res), []

def t_request_gap_ownership(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("gaprequest", [], justification=j)
    return _as_json(res), []

# ===========================================================================
# CAT-7 · Run state
# ===========================================================================

def t_get_element(args: dict) -> tuple[str, list[str]]:
    res = spec_cmd.call("p_element", [], justification="")
    return _as_json(res), []

def t_get_scan_number(args: dict) -> tuple[str, list[str]]:
    res = spec_cmd.call("scan_n", [], justification="")
    return _as_json(res), []

def t_get_current_datafile(args: dict) -> tuple[str, list[str]]:
    res = spec_cmd.call("p_datafile", [], justification="")
    return _as_json(res), []

def t_get_plotselected_counter(args: dict) -> tuple[str, list[str]]:
    res = spec_cmd.call("plotselected", [], justification="")
    return _as_json(res), []

def t_abort_current_scan(args: dict) -> tuple[str, list[str]]:
    j = (args.get("justification") or "").strip()
    res = spec_cmd.call("abort", [], justification=j)
    return _as_json(res), []

def t_recent_actions(args: dict) -> tuple[str, list[str]]:
    experiment_id = spec_cmd.get_experiment_id()
    return _as_json(recent_actions(limit=int(args.get("limit", 20)),
                                   experiment_id=experiment_id)), []

# ---- Data / analysis / plotting handlers (formerly executor.py if/elif) ----

def _analyze_with(
    file_name,
    analyzer,
    e_min=None,
    e_max=None,
    scan_numbers=None,
    include_raw_counts: bool = False,
):
    """Shared shape for convergence and efficiency: load normalized arrays
    (optionally windowed to [e_min, e_max] and/or restricted to scan_numbers),
    run analyzer, attach context.

    If include_raw_counts is True, also load the raw active-counter rate stack
    over the SAME energy window and pass it to the analyzer as
    raw_counts_per_point. The analyzer must accept that kwarg.
    """
    try:
        combined, file_name, counter, used_scans = scan_data.get_normalized_scan_arrays(
            file_name, e_min=e_min, e_max=e_max, scan_numbers=scan_numbers,
        )
    except ValueError as e:
        return {"error": str(e)}
    if len(used_scans) < 2:
        return {"error": f"Need at least 2 scans, found {len(used_scans)}."}

    # Drop rows with NaN in any scan to keep a common grid
    combined_clean = combined.dropna()
    scan_data_2d = combined_clean.values.T.tolist()

    kwargs = {}
    if include_raw_counts:
        try:
            raw_combined, _, _, raw_used = scan_data.get_raw_counter_arrays(
                file_name, scan_numbers=used_scans,
            )
            # Align raw counts to the same energy grid as the windowed normalized stack
            raw_aligned = raw_combined.reindex(combined_clean.index)
            count_times = raw_combined.attrs.get("count_times", [1.0] * len(raw_used))
            # Convert rate -> per-rep total counts at each point: rate * count_time
            raw_total = raw_aligned.values * np.array(count_times)[np.newaxis, :]
            kwargs["raw_counts_per_point"] = raw_total.T.tolist()
        except Exception as e:
            logger.warning("Could not load raw counts for Poisson floor: %s", e)

    result = analyzer(scan_data_2d, **kwargs) if kwargs else analyzer(scan_data_2d)
    if "error" in result:
        return result
    result["file_name"] = file_name
    result["active_counter"] = counter
    result["scan_numbers"] = used_scans
    if e_min is not None and e_max is not None:
        result["energy_window"] = [e_min, e_max]
    return result

def t_get_latest_scan(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    entries = scan_data.list_processed_scans(limit=1)
    if not entries:
        return "No processed scans found.", images_b64
    entry = entries[0]
    trimmed = {
        k: entry[k]
        for k in ("file_name", "scan_number", "scan_command", "date_time", "num_points")
        if k in entry
    }
    return json.dumps(trimmed, indent=2), images_b64

def t_list_scans(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    result = scan_data.list_processed_scans(limit=arguments.get("limit", 20))
    return json.dumps(result, indent=2), images_b64

def t_read_scan(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    file_name = arguments.get("file_name", "")
    scan_number = arguments.get("scan_number", 1)
    meta = scan_data.get_scan_metadata(file_name, scan_number)
    if not meta:
        return "Scan not found.", images_b64
    df = scan_data.read_processed_scan(file_name, scan_number)
    if df is not None:
        meta["data"] = df.to_string()
    return json.dumps(meta, indent=2), images_b64

def t_get_latest_log_entries(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    result = log_reader.get_latest_log_entries(lines=arguments.get("lines", 100))
    return (
        json.dumps(result, indent=2) if result else "No log files found.",
        images_b64,
    )

def t_search_logs(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    result = log_reader.search_logs(
        arguments.get("query", ""),
        max_results=arguments.get("max_results", 50),
    )
    return json.dumps(result, indent=2), images_b64

def t_list_logs(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    result = log_reader.list_logs(limit=arguments.get("limit", 20))
    return json.dumps(result, indent=2), images_b64

def t_get_active_counter(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    result = scan_data.get_active_counter(
        arguments.get("file_name", ""),
        arguments.get("scan_number", 1),
    )
    return (
        json.dumps(result, indent=2) if result else "Scan not found.",
        images_b64,
    )

def t_get_scan_deadtime(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    result = scan_data.get_scan_deadtime(
        arguments.get("file_name", ""),
        arguments.get("scan_number", 1),
    )
    return (
        json.dumps(result, indent=2, default=str)
        if result
        else "Scan not found or no dead time data available.",
        images_b64,
    )

def t_normalize_scan(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    result = scan_data.edge_step_normalize_scan(
        arguments.get("file_name", ""),
        arguments.get("scan_number", 1),
        counter=arguments.get("counter"),
        normalize_by=arguments.get("normalize_by", "I0"),
    )
    return (
        json.dumps(result, indent=2) if result else "Scan not found.",
        images_b64,
    )

def t_average_scans(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    file_name = arguments.get("file_name")
    e_min = arguments.get("e_min")
    e_max = arguments.get("e_max")
    weighting = arguments.get("weighting", "equal")
    if file_name:
        result = scan_data.average_energy_scans(
            file_name=file_name, e_min=e_min, e_max=e_max, weighting=weighting,
        )
    else:
        result = scan_data.average_latest_energy_scans(
            e_min=e_min, e_max=e_max, weighting=weighting,
        )
    return json.dumps(result, indent=2), images_b64

def t_analyze_convergence(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    from beamtimehero_cli.generic_data.cosine_similarity import analyze_scan_quality
    e_min = arguments.get("e_min")
    e_max = arguments.get("e_max")
    if e_min is None or e_max is None:
        return json.dumps({"error": "e_min and e_max are required"}), []
    result = _analyze_with(
        arguments.get("file_name"),
        analyze_scan_quality,
        e_min=e_min,
        e_max=e_max,
    )
    return json.dumps(result, indent=2, default=str), images_b64

def t_analyze_efficiency(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    from beamtimehero_cli.experiment_planning.scan_efficiency import analyze_scan_efficiency
    e_min = arguments.get("e_min")
    e_max = arguments.get("e_max")
    if e_min is None or e_max is None:
        return json.dumps({"error": "e_min and e_max are required"}), []
    result = _analyze_with(
        arguments.get("file_name"),
        analyze_scan_efficiency,
        e_min=e_min,
        e_max=e_max,
        include_raw_counts=bool(arguments.get("include_poisson_floor", True)),
    )
    return json.dumps(result, indent=2, default=str), images_b64

def t_analyze_feature_evolution(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    from beamtimehero_cli.experiment_planning.scan_features import (
        analyze_feature_evolution,
    )
    file_name = arguments.get("file_name")
    e_min = arguments.get("e_min")
    e_max = arguments.get("e_max")
    statistic = arguments.get("statistic", "max")
    sem_target = float(arguments.get("sem_threshold_frac", 0.01))
    drift_target = float(arguments.get("drift_threshold_frac", 0.01))
    if e_min is None or e_max is None:
        return (
            json.dumps({
                "error": "analyze_feature_evolution requires e_min and e_max (numeric eV bounds)."
            }, indent=2),
            images_b64,
        )
    try:
        combined, file_name, counter, used_scans = (
            scan_data.get_normalized_scan_arrays(file_name)
        )
    except ValueError as e:
        return json.dumps({"error": str(e)}, indent=2), images_b64
    combined = combined.dropna()
    energy = combined.index.values.tolist()
    scan_2d = combined.values.T.tolist()
    result = analyze_feature_evolution(
        scan_2d, energy, e_min, e_max, statistic=statistic,
        sem_threshold_frac=sem_target, drift_threshold_frac=drift_target,
    )
    if isinstance(result, dict):
        result.setdefault("file_name", file_name)
        result.setdefault("active_counter", counter)
        result.setdefault("scan_numbers", used_scans)
    return json.dumps(result, indent=2, default=str), images_b64

def t_group_scans_by_spot(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    file_name = arguments.get("file_name")
    tol_mm = float(arguments.get("tol_mm", 0.05))
    if not file_name:
        return (
            json.dumps({"error": "file_name is required."}, indent=2),
            images_b64,
        )
    result = scan_data.group_scans_by_spot(file_name, tol_mm=tol_mm)
    return json.dumps(result, indent=2, default=str), images_b64

def t_analyze_per_spot(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    from beamtimehero_cli.experiment_planning.scan_efficiency import (
        analyze_scan_efficiency,
    )
    from beamtimehero_cli.experiment_planning.scan_features import (
        heterogeneity_f_statistic,
    )
    file_name = arguments.get("file_name")
    e_min = arguments.get("e_min")
    e_max = arguments.get("e_max")
    tol_mm = float(arguments.get("tol_mm", 0.05))
    if not file_name:
        return (
            json.dumps({"error": "file_name is required."}, indent=2),
            images_b64,
        )
    grouping = scan_data.group_scans_by_spot(file_name, tol_mm=tol_mm)
    if "error" in grouping:
        return json.dumps(grouping, indent=2), images_b64

    per_spot_results = []
    per_spot_arrays = []
    for spot in grouping["spots"]:
        if spot["spot_id"] == -1 or spot["n_scans"] < 2:
            continue
        try:
            combined, _, counter, used = scan_data.get_normalized_scan_arrays(
                file_name,
                e_min=e_min,
                e_max=e_max,
                scan_numbers=spot["scan_numbers"],
            )
        except ValueError as e:
            per_spot_results.append({
                "spot_id": spot["spot_id"],
                "error": str(e),
            })
            continue
        clean = combined.dropna()
        arr_2d = clean.values.T.tolist()
        per_spot_arrays.append(arr_2d)
        eff = analyze_scan_efficiency(arr_2d)
        per_spot_results.append({
            "spot_id": spot["spot_id"],
            "center": spot["center"],
            "scan_numbers": spot["scan_numbers"],
            "n_scans": spot["n_scans"],
            "verdict": eff.get("verdict"),
            "cv_mean_pct": eff.get("cv_mean_pct"),
            "final_convergence": eff.get("convergence", {}).get(
                "cumulative_convergence", [None]
            )[-1],
        })

    heterogeneity = None
    if len(per_spot_arrays) >= 2:
        # Trim each spot's stack to the minimum n_points across spots
        min_pts = min(len(a[0]) for a in per_spot_arrays)
        trimmed = [[row[:min_pts] for row in a] for a in per_spot_arrays]
        heterogeneity = heterogeneity_f_statistic(trimmed)

    return (
        json.dumps({
            "file_name": file_name,
            "energy_window": [e_min, e_max] if (e_min is not None and e_max is not None) else None,
            "tol_mm": tol_mm,
            "n_spots_analyzed": len(per_spot_results),
            "per_spot": per_spot_results,
            "heterogeneity": heterogeneity,
        }, indent=2, default=str),
        images_b64,
    )

def t_plot_averaged_scans(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    file_names = arguments.get("file_names", [])
    if not file_names:
        return "Error: file_names array must not be empty.", images_b64
    fig, summary = plotting.plot_averaged_scans_overlay(file_names)
    if fig:
        images_b64.append(fig_to_base64(fig))
        import matplotlib.pyplot as plt
        plt.close(fig)
    return summary, images_b64

def t_plot_scan(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    fig, summary = plotting.plot_scan(
        arguments.get("file_name", ""),
        arguments.get("scan_number", 1),
        counter=arguments.get("counter"),
        normalize_by=arguments.get("normalize_by"),
    )
    if fig:
        images_b64.append(fig_to_base64(fig))
        import matplotlib.pyplot as plt
        plt.close(fig)
    return summary, images_b64

def t_plot_scan_stack(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    fig, summary = plotting.plot_scan_stack(
        arguments.get("file_name", ""),
        e_min=arguments.get("e_min"),
        e_max=arguments.get("e_max"),
    )
    if fig:
        images_b64.append(fig_to_base64(fig))
        import matplotlib.pyplot as plt
        plt.close(fig)
    return summary, images_b64

def t_plot_first_half_vs_second_half(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    fig, summary = plotting.plot_first_half_vs_second_half(
        arguments.get("file_name", ""),
        e_min=arguments.get("e_min"),
        e_max=arguments.get("e_max"),
    )
    if fig:
        images_b64.append(fig_to_base64(fig))
        import matplotlib.pyplot as plt
        plt.close(fig)
    return summary, images_b64

def t_plot_running_average(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    fig, summary = plotting.plot_running_average(
        arguments.get("file_name", ""),
        e_min=arguments.get("e_min"),
        e_max=arguments.get("e_max"),
    )
    if fig:
        images_b64.append(fig_to_base64(fig))
        import matplotlib.pyplot as plt
        plt.close(fig)
    return summary, images_b64

def t_plot_feature_evolution(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    fig, summary = plotting.plot_feature_evolution(
        arguments.get("file_name", ""),
        e_min=arguments.get("e_min"),
        e_max=arguments.get("e_max"),
        statistic=arguments.get("statistic", "max"),
    )
    if fig:
        images_b64.append(fig_to_base64(fig))
        import matplotlib.pyplot as plt
        plt.close(fig)
    return summary, images_b64

def t_plot_data(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    from beamtimehero_cli.spec_data.plotting import plt

    x = arguments.get("x", [])
    series = [arguments.get("y", [])]
    for key in ("y2", "y3", "y4"):
        s = arguments.get(key)
        if s:
            series.append(s)

    if not x or not series[0]:
        return "Error: x and y arrays must not be empty.", images_b64

    for i, y_vals in enumerate(series):
        if len(y_vals) != len(x):
            return (
                f"Error: series {i+1} has {len(y_vals)} points but x has {len(x)}.",
                images_b64,
            )

    labels = arguments.get("labels", [])
    xlabel = arguments.get("xlabel", "")
    ylabel = arguments.get("ylabel", "")
    title = arguments.get("title", "")

    fig, ax = plt.subplots(figsize=(10, 6))
    for i, y_vals in enumerate(series):
        label = labels[i] if i < len(labels) else None
        ax.plot(x, y_vals, linewidth=1.2, label=label)
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title, fontsize=11)
    if labels:
        ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()

    images_b64.append(fig_to_base64(fig))
    plt.close(fig)

    summary = f"Plot generated: {title or 'untitled'} ({len(x)} points, {len(series)} series)"
    return summary, images_b64

def t_list_files(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    from beamtimehero_cli.spec_data import local_data
    result = local_data.list_files(pattern=arguments.get("pattern", "*"))
    if not result:
        return "No files found in scan directory.", images_b64
    return json.dumps(result, indent=2), images_b64

def t_read_file(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    from beamtimehero_cli.spec_data import local_data
    content = local_data.read_file(arguments.get("path", ""))
    return content, images_b64

def t_write_summary(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    from beamtimehero_cli.spec_data import local_data
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"beamtimehero_conversation_summary_{ts}.txt"
    rel_path = local_data.write_file(filename, arguments.get("content", ""))
    return f"Summary saved: {rel_path}", images_b64

def t_write_macro(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    from beamtimehero_cli.spec_data import local_data
    from datetime import datetime
    original = arguments.get("original_name", "macro")
    # Strip .mac extension if present to build new name
    base = original.rsplit(".mac", 1)[0] if original.endswith(".mac") else original
    ts = datetime.now().strftime("%Y-%m-%d")
    filename = f"{base}_heroic_{ts}.mac"
    rel_path = local_data.write_file(filename, arguments.get("content", ""))
    return f"Edited macro saved: {rel_path}", images_b64

def t_save_plan(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    import re as _re
    from beamtimehero_cli.config import PLANS_DIR
    filename = (arguments.get("filename") or "").strip()
    content = arguments.get("content") or ""
    overwrite = bool(arguments.get("overwrite", False))
    if not _re.match(r"^[A-Za-z0-9_\-.]+\.md$", filename) or filename.startswith("."):
        return json.dumps({
            "ok": False,
            "error": (
                "filename must match ^[A-Za-z0-9_\\-.]+\\.md$ and not start with "
                "'.' (no path separators, traversal, or hidden files)"
            ),
        }), images_b64
    target = (PLANS_DIR / filename).resolve()
    try:
        target.relative_to(PLANS_DIR.resolve())
    except ValueError:
        return json.dumps({
            "ok": False,
            "error": f"resolved path escapes PLANS_DIR: {target}",
        }), images_b64
    existed = target.exists()
    if existed and not overwrite:
        return json.dumps({
            "ok": False,
            "error": f"file exists: {filename}; pass overwrite=true to replace",
        }), images_b64
    target.write_text(content, encoding="utf-8")
    return json.dumps({
        "ok": True,
        "path": str(target),
        "bytes": len(content.encode("utf-8")),
        "overwrote": existed,
    }, indent=2), images_b64

def t_get_motor_config(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    from beamtimehero_cli.spec_data.spec_config import get_motor_config
    return get_motor_config(), images_b64

def t_get_counter_config(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    from beamtimehero_cli.spec_data.spec_config import get_counter_config
    return get_counter_config(), images_b64

def t_evaluate_spec_macro(arguments: dict) -> tuple[str, list[str]]:
    images_b64: list[str] = []
    from beamtimehero_cli.spec_eval import evaluate_spec_macro
    result = evaluate_spec_macro(
        macro=arguments.get("macro", ""),
        preload=arguments.get("preload"),
        timeout_s=arguments.get("timeout_s", 30),
    )
    return json.dumps(result, indent=2), images_b64

# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

DISPATCH: dict[str, callable] = {
    # CAT-0
    "align_beamline": t_align_beamline,
    "align_xes_spectrometer": t_align_xes,
    "run_sample_alignment": t_auto_sample_align,
    "run_collection": t_run_collection,
    "select_element": t_select_element,
    "peak_mono_pitch": t_peak_mono_pitch,
    "calibrate_mono": t_calibrate_mono,
    # CAT-1
    "move_motor": t_move_motor,
    "move_motor_relative": t_move_motor_relative,
    "read_motor_position": t_read_motor_position,
    "read_all_positions": t_wa,
    # CAT-2
    "run_motor_scan": t_run_motor_scan,
    "run_motor_scan_relative": t_run_motor_scan_relative,
    "run_diagonal_scan": t_run_diagonal_scan,
    "run_xas": t_run_xas,
    "run_emiss_scan": t_run_emiss_scan,
    "fit_emission_peak": t_fit_emission_peak,
    # CAT-3
    "mv_energy": t_mv_energy,
    "shutter": t_shutter,
    "set_filter": t_set_filter,
    "safely_remove_filters": t_safely_remove_filters,
    "set_gain": t_set_gain,
    "set_vortex_roi": t_set_vortex_roi,
    "open_data_file": t_open_data_file,
    "plotselect": t_plotselect,
    # CAT-4
    "run_align_shortcut": t_run_align_shortcut,
    "post_scan_move": t_post_scan_move,
    # CAT-5 (beam diagnostic)
    "mv_pinhole": t_mv_pinhole,
    "mv_plastic": t_mv_plastic,
    "mv_knife_clear": t_mv_knife_clear,
    "mv_knife_out": t_mv_knife_out,
    "measure_beam_size": t_measure_beam_size,
    "zero_pinhole": t_zero_pinhole,
    "small_beam": t_small_beam,
    "big_beam": t_big_beam,
    "xtal_align": t_xtal_align,
    "reset_gap": t_reset_gap,
    "set_m2_stripe": t_set_m2_stripe,
    "get_anchor": t_get_anchor,
    "set_anchor": t_set_anchor,
    "tracking": t_tracking,
    # CAT-6
    "get_beam_size": t_get_beam_size,
    "get_beam_status": t_get_beam_status,
    "get_counts": t_get_counts,
    "get_counter": t_get_counter,
    "request_gap_ownership": t_request_gap_ownership,
    # CAT-7
    "get_element": t_get_element,
    "get_scan_number": t_get_scan_number,
    "get_current_datafile": t_get_current_datafile,
    "get_plotselected_counter": t_get_plotselected_counter,
    "abort_current_scan": t_abort_current_scan,
    "recent_actions": t_recent_actions,
    # Data / analysis / plotting tools (formerly executor.py if/elif)
    "get_latest_scan": t_get_latest_scan,
    "list_scans": t_list_scans,
    "read_scan": t_read_scan,
    "get_latest_log_entries": t_get_latest_log_entries,
    "search_logs": t_search_logs,
    "list_logs": t_list_logs,
    "get_active_counter": t_get_active_counter,
    "get_scan_deadtime": t_get_scan_deadtime,
    "normalize_scan": t_normalize_scan,
    "average_scans": t_average_scans,
    "analyze_convergence": t_analyze_convergence,
    "analyze_efficiency": t_analyze_efficiency,
    "analyze_feature_evolution": t_analyze_feature_evolution,
    "group_scans_by_spot": t_group_scans_by_spot,
    "analyze_per_spot": t_analyze_per_spot,
    "plot_averaged_scans": t_plot_averaged_scans,
    "plot_scan": t_plot_scan,
    "plot_scan_stack": t_plot_scan_stack,
    "plot_first_half_vs_second_half": t_plot_first_half_vs_second_half,
    "plot_running_average": t_plot_running_average,
    "plot_feature_evolution": t_plot_feature_evolution,
    "plot_data": t_plot_data,
    "list_files": t_list_files,
    "read_file": t_read_file,
    "write_summary": t_write_summary,
    "write_macro": t_write_macro,
    "save_plan": t_save_plan,
    "get_motor_config": t_get_motor_config,
    "get_counter_config": t_get_counter_config,
    "evaluate_spec_macro": t_evaluate_spec_macro,
}
