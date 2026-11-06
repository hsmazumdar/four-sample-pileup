"""Run the segment-first validation and write aggregate tables.

    python -m sparse_pileup.strict_validation --out artifacts/v6

Historical V5 files under artifacts/v5_* are not overwritten.
Per-event waveforms are not written.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import csv
import hashlib
import json
import platform
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sparse_pileup.constants import (  # noqa: E402
    ADC_CHANNELS,
    CR_RC_TAU_SAMPLES,
    DEFAULT_EPOCHS,
    DEFAULT_SEED,
    PEDESTAL_CH,
)
from sparse_pileup.dataset import generate_events  # noqa: E402
from sparse_pileup.dual_head import DualHeadDetector  # noqa: E402
from sparse_pileup.flex_mlp import FlexMLP  # noqa: E402
from sparse_pileup.ls_peak import LsPeakEstimator  # noqa: E402
from sparse_pileup.metrics import peak_metrics, pileup_metrics, roc_auc  # noqa: E402
from sparse_pileup.mlp import SmallMLP  # noqa: E402
from sparse_pileup.operating_region import score_retrigger, score_residual, score_slope  # noqa: E402
from sparse_pileup.real_pulse_lib import load_library  # noqa: E402
from sparse_pileup.sampler import extract_n_taps  # noqa: E402
from sparse_pileup.segment_protocol import (  # noqa: E402
    COINCIDENCE_SAMPLES,
    EPOCHS,
    EXTRA_NOISE_CH,
    GAPS,
    N_CELL,
    N_STREAM_PULSES,
    N_TEST_PREV,
    N_TRAIN,
    N_VAL,
    PRIMARY_RUN,
    PROTOCOL_PUBLIC,
    RATIOS,
    amp_summary,
    campaign_rates,
    fit_logistic,
    fit_template,
    height_errors,
    historical_pulse_leakage,
    make_balanced,
    make_conditional_events,
    prf_counts,
    prepare_split,
    rate_grid,
    scan_campaign,
    score_logistic,
    select_threshold,
    synthesize_stream,
)


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _jsonable(obj.tolist())
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    return obj


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    seen = set()
    for row in rows:
        for k in row:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in keys})


def _sha256_text(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _train_mlp(events: list[dict], rng: np.random.Generator, epochs: int = EPOCHS) -> SmallMLP:
    net = SmallMLP.random(rng)
    xs = [ev["samples"] for ev in events]
    ys = [1.0 if ev["is_pileup"] else 0.0 for ev in events]
    order = np.arange(len(xs))
    for _ in range(epochs):
        rng.shuffle(order)
        for i in order:
            net.train_step(xs[i], ys[i])
    return net


def _train_flex(events: list[dict], rng: np.random.Generator, n_in: int, stride: int, epochs: int) -> FlexMLP:
    net = FlexMLP.random(n_in, rng)
    xs, ys = [], []
    for ev in events:
        fr = extract_n_taps(ev["waveform"], n_in, stride)
        if fr is None:
            continue
        xs.append(fr.samples)
        ys.append(1.0 if ev["is_pileup"] else 0.0)
    order = np.arange(len(xs))
    for _ in range(epochs):
        rng.shuffle(order)
        for i in order:
            net.train_step(xs[i], ys[i])
    return net


def _pack_scores(events: list[dict], net: SmallMLP, log_w: np.ndarray, est: LsPeakEstimator) -> dict[str, np.ndarray]:
    mlp, ret, slope, resid, logistic, labels = [], [], [], [], [], []
    for ev in events:
        prob, _ = net.forward(ev["samples"])
        mlp.append(float(prob))
        ret.append(score_retrigger(ev["waveform"]))
        slope.append(score_slope(ev["samples"]))
        resid.append(score_residual(ev["samples"], est))
        logistic.append(score_logistic(ev["samples"], log_w))
        labels.append(1 if ev["is_pileup"] else 0)
    return {
        "mlp": np.asarray(mlp, dtype=np.float64),
        "retrigger": np.asarray(ret, dtype=np.float64),
        "slope": np.asarray(slope, dtype=np.float64),
        "residual": np.asarray(resid, dtype=np.float64),
        "logistic": np.asarray(logistic, dtype=np.float64),
        "y": np.asarray(labels, dtype=np.int32),
    }


def _or_scores(mlp: np.ndarray, retrigger: np.ndarray, mlp_thr: float) -> np.ndarray:
    """Binary fusion. ``mlp_thr`` is the validation cut on the MLP probability.

    The returned score is 0 or 1. A later cut of 0.5 on that score is only
    the decision on an already binary value. It is not a second MLP threshold.
    """
    return np.where((mlp >= mlp_thr) | (retrigger >= 0.5), 1.0, 0.0)


def annotate_threshold_metadata(rows: list[dict], mlp_threshold_by_run: dict[str, str]) -> None:
    """Name what the stored ``threshold`` cell means. Does not rescore."""
    for row in rows:
        method = str(row.get("method", ""))
        run = str(row.get("run_id", ""))
        mlp_thr = mlp_threshold_by_run.get(run, "")
        if method == "mlp_or_retrigger":
            row["mlp_leg_threshold"] = mlp_thr
            row["retrigger_leg_threshold"] = "0.5"
            row["threshold_column_meaning"] = "cut_on_binary_or_score"
            row["threshold_source"] = "validation_mlp_OR_retrigger_hard"
        elif method == "mlp":
            row["mlp_leg_threshold"] = row.get("threshold", mlp_thr)
            row["retrigger_leg_threshold"] = ""
            row["threshold_column_meaning"] = "cut_on_mlp_probability"
        elif method == "mlp@0.5":
            row["mlp_leg_threshold"] = "0.5"
            row["retrigger_leg_threshold"] = ""
            row["threshold_column_meaning"] = "historical_fixed_0.5_cut_on_mlp_probability"
        elif method == "retrigger":
            row["mlp_leg_threshold"] = ""
            row["retrigger_leg_threshold"] = "0.5"
            row["threshold_column_meaning"] = "hard_retrigger_score"
        elif method == "slope":
            row["mlp_leg_threshold"] = ""
            row["retrigger_leg_threshold"] = ""
            row["threshold_column_meaning"] = "hard_slope_score"
        elif str(method).startswith("logistic"):
            row["mlp_leg_threshold"] = ""
            row["retrigger_leg_threshold"] = ""
            row["threshold_column_meaning"] = "cut_on_logistic_probability"
        elif str(method).startswith("residual"):
            row["mlp_leg_threshold"] = ""
            row["retrigger_leg_threshold"] = ""
            row["threshold_column_meaning"] = "cut_on_template_residual"
        else:
            row["mlp_leg_threshold"] = ""
            row["retrigger_leg_threshold"] = ""
            row["threshold_column_meaning"] = "cut_on_method_score"


def _metric_row(run_id: str, method: str, scores: np.ndarray, y: np.ndarray, thr: float, **extra) -> dict:
    row = {"run_id": run_id, "method": method, "auc": roc_auc(scores, y)}
    row.update(prf_counts(scores, y, thr))
    row.update(extra)
    return row


def _historical_block() -> dict:
    """Reproduce the published test file and separate the 21.1 / 21.9 protocols."""
    csv_path = ROOT / "config" / "sdd_fe55_lines.csv"
    rows = generate_events(1000, csv_path, DEFAULT_SEED + 2, engine="real", split_name="test")
    model = DualHeadDetector.load_json(ROOT / "weights" / "dual_head.json")
    pile = pileup_metrics(model, rows)
    iso = peak_metrics(model, rows, isolated_only=True)
    archived = json.loads((ROOT / "artifacts" / "v5_summary.json").read_text(encoding="utf-8"))
    lib = load_library(ROOT)
    _tr, _va, te = lib.split(DEFAULT_SEED)
    tr, _va2, _te2 = lib.split(DEFAULT_SEED)
    rng = np.random.default_rng(DEFAULT_SEED + 5)
    frozen = height_errors(te.snippets, rng, estimator=LsPeakEstimator())
    rng_emp = np.random.default_rng(DEFAULT_SEED + 5)
    hist_ids = tuple(sorted({s.segment_index for s in tr.snippets}))
    # Train pulses still come from every buffer. This is the leaky V5 template.
    hist_template = fit_template(tr.snippets, hist_ids)
    empirical = height_errors(
        te.snippets,
        rng_emp,
        template=hist_template.mean_unit,
        pedestal_ch=PEDESTAL_CH,
        empirical_step=0.2,
    )
    rng_emp_01 = np.random.default_rng(DEFAULT_SEED + 5)
    empirical_01 = height_errors(
        te.snippets,
        rng_emp_01,
        template=hist_template.mean_unit,
        pedestal_ch=hist_template.pedestal_ch,
        empirical_step=0.1,
    )
    return {
        "official_test_file": {
            "n": pile.n,
            "n_pileup": pile.n_pileup,
            "tp": pile.tp,
            "fp": pile.fp,
            "tn": pile.tn,
            "fn": pile.fn,
            "precision": pile.precision,
            "recall": pile.recall,
            "f1": pile.f1,
            "isolated_n": iso.n,
            "isolated_mae_ch": iso.mae_ch,
            "isolated_rmse_ch": iso.rmse_ch,
            "isolated_max_ch": iso.max_ch,
            "protocol": "pulse-level split seed 42, frozen weights, threshold 0.5, test seed 44, n=1000",
        },
        "archived_v5_summary_kernel_mae_ch": archived.get("kernel_mae_ch"),
        "archived_v5_summary_empirical_mae_ch": archived.get("empirical_mae_ch"),
        "archived_v5_summary_sha256": _sha256_text(ROOT / "artifacts" / "v5_summary.json"),
        "all_historical_test_snippets_frozen_template": frozen,
        "all_historical_test_snippets_empirical_step_0.2_published_pedestal": empirical,
        "all_historical_test_snippets_empirical_step_0.1_train_pedestal": empirical_01,
        "note": (
            "21.9 ch is the official 905-event isolated subset. "
            "21.1 ch is the archived operating_region draw of up to 400 isolated "
            "events after that script's RNG had already been consumed. "
            "The all-snippet rows use every historical test snippet once."
        ),
    }


def _mae_suite(prep, run_id: str) -> list[dict]:
    frozen = LsPeakEstimator()
    refit = LsPeakEstimator(
        pedestal=prep.template.pedestal_ch / ADC_CHANNELS,
        tau=prep.template.tau_samples,
    )
    specs = [
        ("frozen_published_crrc8_n4", frozen, None, PEDESTAL_CH, (0, 4, 8, 12), 0.1),
        ("train_refit_crrc8_n4", refit, None, prep.template.pedestal_ch, (0, 4, 8, 12), 0.1),
        ("train_empirical_n4", None, prep.template.mean_unit, prep.template.pedestal_ch, (0, 4, 8, 12), 0.1),
        ("frozen_published_crrc8_n8", frozen, None, PEDESTAL_CH, (0, 2, 4, 6, 8, 10, 12, 14), 0.1),
        ("train_refit_crrc8_n8", refit, None, prep.template.pedestal_ch, (0, 2, 4, 6, 8, 10, 12, 14), 0.1),
        ("train_empirical_n8", None, prep.template.mean_unit, prep.template.pedestal_ch, (0, 2, 4, 6, 8, 10, 12, 14), 0.1),
    ]
    rows = []
    for name, est, tmpl, ped, offs, step in specs:
        stats = height_errors(
            prep.test,
            np.random.default_rng(prep.seed + 5),
            estimator=est,
            template=tmpl,
            pedestal_ch=ped,
            offsets=offs,
            empirical_step=step,
        )
        stats.update({"run_id": run_id, "estimator": name, "split": "test_snippets_one_placement"})
        rows.append(stats)
    return rows


def _stream_method_rows(run_id: str, rate: dict, records: list[dict], meta: dict, net, log_w, est, thresholds: dict) -> list[dict]:
    matched = [r for r in records if r.get("matched")]
    if not matched:
        return []
    scores = {
        "mlp": np.array([net.forward(r["samples"])[0] for r in matched], dtype=np.float64),
        "retrigger": np.array([score_retrigger(r["waveform"]) for r in matched], dtype=np.float64),
        "slope": np.array([score_slope(r["samples"]) for r in matched], dtype=np.float64),
        "residual": np.array([score_residual(r["samples"], est) for r in matched], dtype=np.float64),
        "logistic": np.array([score_logistic(r["samples"], log_w) for r in matched], dtype=np.float64),
    }
    scores["mlp_or_retrigger"] = _or_scores(scores["mlp"], scores["retrigger"], thresholds["mlp"])
    label_sets = {
        "either_neighbor_within_2us": np.array([1 if r["label_either_2us"] else 0 for r in matched], dtype=np.int32),
        "either_neighbor_within_4us": np.array([1 if r["label_either_4us"] else 0 for r in matched], dtype=np.int32),
        "forward_neighbor_within_2us": None,
    }
    forward = []
    forward_idx = []
    for i, r in enumerate(matched):
        if r["backward_only"]:
            continue
        forward.append(1 if r["label_forward_2us"] else 0)
        forward_idx.append(i)
    forward_idx = np.array(forward_idx, dtype=np.int32)
    label_sets["forward_neighbor_within_2us"] = np.array(forward, dtype=np.int32)
    rows = []
    hard = {"retrigger": 0.5, "slope": 0.5, "mlp_or_retrigger": 0.5}
    for label_name, y in label_sets.items():
        for method, sc in scores.items():
            use = sc[forward_idx] if label_name == "forward_neighbor_within_2us" else sc
            thr = hard[method] if method in hard else thresholds[method]
            row = _metric_row(
                run_id,
                method,
                use,
                y,
                thr,
                study="unconditional_stream",
                label_rule=label_name,
                rate_tag=rate["tag"],
                rate_hz=rate["rate_hz"],
                modelling_assumption=rate["modelling_assumption"],
                modelling_p_forward_within_2us=rate["modelling_p_forward_within_2us"],
                n_pulses_drawn=meta["n_pulses_drawn"],
                n_unmatched_triggers=meta["n_triggers_unmatched"],
                n_saturated_high_samples=meta["n_saturated_high_samples"],
                n_below_zero_samples=meta["n_below_zero_samples"],
                n_triple_among_matched=int(sum(r["n_other_within_2us"] >= 2 for r in matched)),
            )
            row["recall_unstable"] = bool(row["n_pos"] < 30)
            rows.append(row)
    # Gap bins use the forward neighbor of matched triggers. Primary label context.
    bins = ((0, 4), (4, 8), (8, 12), (12, 16), (16, 20))
    dt = np.array([r["dt_next"] if r["dt_next"] is not None else -1 for r in matched])
    for lo, hi in bins:
        mask = (dt > lo) & (dt <= hi)
        if int(mask.sum()) == 0:
            continue
        y = np.ones(int(mask.sum()), dtype=np.int32)
        for method in ("mlp", "retrigger", "residual", "logistic", "slope", "mlp_or_retrigger"):
            thr = hard[method] if method in hard else thresholds[method]
            sc = scores[method][mask]
            # Every event in the bin is a forward pile-up, so recall equals the positive rate.
            m = prf_counts(sc, y, thr)
            rows.append(
                {
                    "run_id": run_id,
                    "method": method,
                    "study": "unconditional_stream_gap_bin",
                    "label_rule": "forward_gap_bin_all_positive",
                    "rate_tag": rate["tag"],
                    "rate_hz": rate["rate_hz"],
                    "gap_lo_samples": lo,
                    "gap_hi_samples": hi,
                    "gap_lo_us": lo * 0.1,
                    "gap_hi_us": hi * 0.1,
                    "n_pos": m["n_pos"],
                    "recall": m["recall"],
                    "tp": m["tp"],
                    "fn": m["fn"],
                    "threshold": thr,
                    "modelling_assumption": rate["modelling_assumption"],
                    "recall_unstable": bool(m["n_pos"] < 30),
                }
            )
    return rows


def run_one(campaign, mode: str, seed: int, *, full_maps: bool) -> dict:
    prep = prepare_split(campaign, mode, seed)
    print(
        f"run {prep.run_id}  snippets {len(prep.train)}/{len(prep.val)}/{len(prep.test)}  "
        f"tau={prep.template.tau_samples:.4f}  pedestal={prep.template.pedestal_ch:.2f}",
        flush=True,
    )
    train_rng = np.random.default_rng(seed)
    val_rng = np.random.default_rng(seed + 1)
    test_rng = np.random.default_rng(seed + 2)
    init_rng = np.random.default_rng(seed + 99)
    log_rng = np.random.default_rng(seed + 123)
    cell_rng = np.random.default_rng(seed + 7)
    stream_rng = np.random.default_rng(seed + 11)

    train = make_conditional_events(prep.train, train_rng, N_TRAIN)
    val = make_conditional_events(prep.val, val_rng, N_VAL)
    test = make_conditional_events(prep.test, test_rng, N_TEST_PREV)
    est = LsPeakEstimator(
        pedestal=prep.template.pedestal_ch / ADC_CHANNELS,
        tau=prep.template.tau_samples,
    )
    net = _train_mlp(train, init_rng, EPOCHS)
    x_train = np.stack([ev["samples"] for ev in train])
    y_train = np.array([1.0 if ev["is_pileup"] else 0.0 for ev in train])
    log_w = fit_logistic(x_train, y_train, log_rng)

    val_scores = _pack_scores(val, net, log_w, est)
    thresholds = {}
    threshold_audit = {}
    for method in ("mlp", "logistic", "residual"):
        mode = "quantile" if method == "residual" else "probability"
        thr, f1 = select_threshold(val_scores[method], val_scores["y"], mode=mode)
        thresholds[method] = thr
        at05 = prf_counts(val_scores[method], val_scores["y"], 0.5)
        threshold_audit[method] = {
            "selected": thr,
            "val_f1_at_selected": f1,
            "val_f1_at_0.5": at05["f1"],
            "rule": "max F1 on validation prevalence mix; higher threshold wins ties",
        }
    thresholds["retrigger"] = 0.5
    thresholds["slope"] = 0.5
    threshold_audit["retrigger"] = {"selected": 0.5, "rule": "hard decision, not tuned"}
    threshold_audit["slope"] = {"selected": 0.5, "rule": "hard decision, not tuned"}

    test_scores = _pack_scores(test, net, log_w, est)
    test_scores["mlp_or_retrigger"] = _or_scores(test_scores["mlp"], test_scores["retrigger"], thresholds["mlp"])
    prev_rows = []
    for method, sc in test_scores.items():
        if method == "y":
            continue
        thr = 0.5 if method in ("retrigger", "slope", "mlp_or_retrigger") else thresholds[method]
        prev_rows.append(
            _metric_row(
                prep.run_id,
                method,
                sc,
                test_scores["y"],
                thr,
                study="conditional_prevalence_mix",
                pileup_period=10,
                threshold_source="validation_prevalence_mix" if method in thresholds and method not in ("retrigger", "slope") else "fixed",
            )
        )
        if method in ("mlp", "logistic", "residual"):
            prev_rows.append(
                _metric_row(
                    prep.run_id,
                    method + "@0.5",
                    sc,
                    test_scores["y"],
                    0.5,
                    study="conditional_prevalence_mix_threshold_0.5",
                    threshold_source="historical_fixed_0.5",
                )
            )

    mae_rows = _mae_suite(prep, prep.run_id)

    gap_rows = []
    for gap in GAPS:
        events = make_balanced(prep.test, cell_rng, N_CELL, gap=gap)
        packed = _pack_scores(events, net, log_w, est)
        packed["mlp_or_retrigger"] = _or_scores(packed["mlp"], packed["retrigger"], thresholds["mlp"])
        for method, sc in packed.items():
            if method == "y":
                continue
            thr = 0.5 if method in ("retrigger", "slope", "mlp_or_retrigger") else thresholds[method]
            gap_rows.append(
                _metric_row(
                    prep.run_id,
                    method,
                    sc,
                    packed["y"],
                    thr,
                    study="conditional_two_pulse_gap",
                    gap_samples=gap,
                    gap_us=gap * 0.1,
                    target_ratio="natural_fe55",
                    n_saturated_events=int(sum(ev["n_saturated_high"] > 0 for ev in events)),
                )
            )
        gap_rows.append(
            _metric_row(
                prep.run_id,
                "mlp@0.5",
                packed["mlp"],
                packed["y"],
                0.5,
                study="conditional_two_pulse_gap",
                gap_samples=gap,
                gap_us=gap * 0.1,
                target_ratio="natural_fe55",
                threshold_source="historical_fixed_0.5",
            )
        )

    ratio_rows = []
    ratio_gaps = GAPS if full_maps else (4, 8, 12, 16, 20)
    for gap in ratio_gaps:
        for ratio in RATIOS:
            events = make_balanced(prep.test, cell_rng, N_CELL, gap=gap, target_ratio=float(ratio))
            packed = _pack_scores(events, net, log_w, est)
            packed["mlp_or_retrigger"] = _or_scores(packed["mlp"], packed["retrigger"], thresholds["mlp"])
            for method, sc in packed.items():
                if method == "y":
                    continue
                thr = 0.5 if method in ("retrigger", "slope", "mlp_or_retrigger") else thresholds[method]
                ratio_rows.append(
                    _metric_row(
                        prep.run_id,
                        method,
                        sc,
                        packed["y"],
                        thr,
                        study="conditional_two_pulse_ratio",
                        gap_samples=gap,
                        gap_us=gap * 0.1,
                        ratio=float(ratio),
                        outside_measured_fe55_ratio_range=bool(ratio < 0.8 or ratio > 1.25),
                        n_saturated_events=int(sum(ev["n_saturated_high"] > 0 for ev in events)),
                        n_events=len(events),
                    )
                )
            ratio_rows.append(
                _metric_row(
                    prep.run_id,
                    "mlp@0.5",
                    packed["mlp"],
                    packed["y"],
                    0.5,
                    study="conditional_two_pulse_ratio",
                    gap_samples=gap,
                    gap_us=gap * 0.1,
                    ratio=float(ratio),
                    threshold_source="historical_fixed_0.5",
                )
            )

    noise_rows = []
    if full_maps:
        for sigma in EXTRA_NOISE_CH:
            events = make_balanced(prep.test, cell_rng, N_CELL, extra_noise_ch=float(sigma))
            packed = _pack_scores(events, net, log_w, est)
            packed["mlp_or_retrigger"] = _or_scores(packed["mlp"], packed["retrigger"], thresholds["mlp"])
            for method in ("mlp", "retrigger", "residual", "logistic", "mlp_or_retrigger"):
                thr = 0.5 if method in ("retrigger", "mlp_or_retrigger") else thresholds[method]
                noise_rows.append(
                    _metric_row(
                        prep.run_id,
                        method,
                        packed[method],
                        packed["y"],
                        thr,
                        study="conditional_added_noise_stress",
                        extra_noise_ch=float(sigma),
                        note="Gaussian added on top of measured noise; threshold stays the clean validation threshold",
                    )
                )

    rates = rate_grid(campaign_rates(campaign)["rate_fe55_hz"])
    stream_rows = []
    for rate in rates:
        print(f"  stream {prep.run_id} {rate['tag']} {rate['rate_hz']:.1f} Hz", flush=True)
        records, meta = synthesize_stream(
            prep.test,
            prep.baseline_pool,
            stream_rng,
            rate_hz=float(rate["rate_hz"]),
            n_pulses=N_STREAM_PULSES,
        )
        stream_rows.extend(_stream_method_rows(prep.run_id, rate, records, meta, net, log_w, est, thresholds))

    n8_rows = []
    if full_maps:
        flex_rng = np.random.default_rng(seed + 77)
        flex = _train_flex(train, flex_rng, 8, 2, EPOCHS)
        def flex_scores(events):
            sc, y = [], []
            for ev in events:
                fr = extract_n_taps(ev["waveform"], 8, 2)
                if fr is None:
                    continue
                sc.append(flex.forward(fr.samples))
                y.append(1 if ev["is_pileup"] else 0)
            return np.array(sc), np.array(y, dtype=np.int32)
        vsc, vy = flex_scores(val)
        thr8, _ = select_threshold(vsc, vy)
        tsc, ty = flex_scores(test)
        n8_rows.append(
            _metric_row(
                prep.run_id,
                "flex_8tap",
                tsc,
                ty,
                thr8,
                study="conditional_prevalence_mix",
                n_in=8,
                stride=2,
                epochs=EPOCHS,
                threshold_source="validation_prevalence_mix",
            )
        )
        for gap in GAPS:
            events = make_balanced(prep.test, cell_rng, N_CELL // 2, gap=gap)
            sc, y = flex_scores(events)
            n8_rows.append(
                _metric_row(
                    prep.run_id,
                    "flex_8tap",
                    sc,
                    y,
                    thr8,
                    study="conditional_two_pulse_gap",
                    gap_samples=gap,
                    gap_us=gap * 0.1,
                    n_in=8,
                    stride=2,
                )
            )

    return {
        "run_id": prep.run_id,
        "mode": mode,
        "seed": seed,
        "n_train_segments": len(prep.train_ids),
        "n_val_segments": len(prep.val_ids),
        "n_test_segments": len(prep.test_ids),
        "train_ids": list(prep.train_ids),
        "val_ids": list(prep.val_ids),
        "test_ids": list(prep.test_ids),
        "n_train_snippets": len(prep.train),
        "n_val_snippets": len(prep.val),
        "n_test_snippets": len(prep.test),
        "amplitude_train": amp_summary(prep.train),
        "amplitude_val": amp_summary(prep.val),
        "amplitude_test": amp_summary(prep.test),
        "template": {
            "n_snippets": prep.template.n_snippets,
            "tau_samples": prep.template.tau_samples,
            "fit_mse": prep.template.fit_mse,
            "pedestal_ch": prep.template.pedestal_ch,
            "baseline_sigma_ch": prep.template.baseline_sigma_ch,
            "support_pre_samples": prep.template.support_pre_samples,
            "support_post_samples": prep.template.support_post_samples,
            "published_tau_samples": CR_RC_TAU_SAMPLES,
            "published_pedestal_ch": PEDESTAL_CH,
            "segment_ids_are_train_only": True,
        },
        "baseline_pool_n": int(prep.baseline_pool.size),
        "thresholds": threshold_audit,
        "train_n_pileup": int(sum(ev["is_pileup"] for ev in train)),
        "val_n_pileup": int(sum(ev["is_pileup"] for ev in val)),
        "test_n_pileup": int(sum(ev["is_pileup"] for ev in test)),
        "prevalence_rows": prev_rows,
        "mae_rows": mae_rows,
        "gap_rows": gap_rows,
        "ratio_rows": ratio_rows,
        "noise_rows": noise_rows,
        "stream_rows": stream_rows,
        "n8_rows": n8_rows,
    }


def _agg_key(value):
    if isinstance(value, (float, np.floating)):
        return round(float(value), 6)
    return value


def _aggregate(rows: list[dict], group_name: str, run_ids: set[str], keys: list[str]) -> list[dict]:
    grouped: dict[tuple, list] = {}
    for row in rows:
        if row.get("run_id") not in run_ids:
            continue
        ident = tuple(_agg_key(row.get(k)) for k in keys)
        grouped.setdefault(ident, []).append(row)
    out = []
    for ident, items in grouped.items():
        for metric in ("f1", "recall", "precision", "fpr", "auc", "mae_ch", "bias_ch"):
            vals = [float(it[metric]) for it in items if it.get(metric) not in (None, "")]
            if len(vals) < 2:
                continue
            rec = {
                "group": group_name,
                "metric": metric,
                "n_runs": len(vals),
                "mean": float(np.mean(vals)),
                "std": float(np.std(vals, ddof=1)),
                "min": float(np.min(vals)),
                "max": float(np.max(vals)),
            }
            for k, v in zip(keys, ident):
                rec[k] = v
            out.append(rec)
    return out


def _plots(out: Path, result: dict) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    written = []
    primary = result["primary_run_id"]
    gaps = [r for r in result["gap_rows"] if r["run_id"] == primary]
    fig, ax = plt.subplots(figsize=(6.4, 3.6), dpi=140)
    for method, color, ls in (
        ("mlp", "#1F4E79", "-"),
        ("retrigger", "#7F8C8D", "--"),
        ("residual", "#C0392B", "--"),
        ("logistic", "#27AE60", ":"),
        ("mlp_or_retrigger", "#000000", "-."),
    ):
        rows = sorted((r for r in gaps if r["method"] == method), key=lambda r: r["gap_us"])
        if not rows:
            continue
        ax.plot([r["gap_us"] for r in rows], [r["recall"] for r in rows], ls, color=color, marker="o", ms=3.5, label=method)
    ax.set_xlabel("Peak-to-peak gap (µs)")
    ax.set_ylabel("Recall on balanced conditional pairs")
    ax.set_ylim(-0.02, 1.05)
    ax.set_title(f"Conditional two-pulse gap study ({primary})")
    ax.legend(frameon=False, fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    p = out / "conditional_recall_vs_gap.png"
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    written.append(p.name)

    ratios = [r for r in result["ratio_rows"] if r["run_id"] == primary and r["method"] == "mlp"]
    if ratios:
        gap_vals = sorted({r["gap_us"] for r in ratios})
        ratio_vals = sorted({r["ratio"] for r in ratios})
        z = np.full((len(ratio_vals), len(gap_vals)), np.nan)
        gi = {g: i for i, g in enumerate(gap_vals)}
        ri = {a: i for i, a in enumerate(ratio_vals)}
        for r in ratios:
            z[ri[r["ratio"]], gi[r["gap_us"]]] = r["f1"]
        fig, axes = plt.subplots(1, 3, figsize=(9.6, 3.3), dpi=140, sharey=True)
        for ax, method, title in zip(
            axes,
            ("mlp", "retrigger", "mlp_or_retrigger"),
            ("4-5-1 MLP", "Retrigger", "MLP OR retrigger"),
        ):
            zz = np.full_like(z, np.nan)
            for r in result["ratio_rows"]:
                if r["run_id"] != primary or r["method"] != method:
                    continue
                zz[ri[r["ratio"]], gi[r["gap_us"]]] = r["f1"]
            im = ax.imshow(zz, origin="lower", aspect="auto", vmin=0, vmax=1, cmap="viridis")
            ax.set_xticks(range(len(gap_vals)), [f"{g:.1f}" for g in gap_vals], fontsize=7)
            ax.set_yticks(range(len(ratio_vals)), [f"{a:g}" for a in ratio_vals])
            ax.set_xlabel("Δt (µs)")
            ax.set_title(title, fontsize=10)
        axes[0].set_ylabel("Constructed A2/A1")
        fig.colorbar(im, ax=axes, fraction=0.046, label="Balanced F1")
        fig.suptitle(f"Conditional operating region ({primary})", fontsize=11)
        p = out / "conditional_f1_heatmap.png"
        fig.savefig(p, bbox_inches="tight")
        plt.close(fig)
        written.append(p.name)

    stream = [
        r
        for r in result["stream_rows"]
        if r["run_id"] == primary
        and r.get("study") == "unconditional_stream"
        and r.get("label_rule") == "either_neighbor_within_2us"
        and r["method"] in ("mlp", "retrigger", "mlp_or_retrigger")
    ]
    if stream:
        fig, ax1 = plt.subplots(figsize=(6.6, 3.6), dpi=140)
        tags = []
        for r in stream:
            if r["rate_tag"] not in tags:
                tags.append(r["rate_tag"])
        order = {t: i for i, t in enumerate(tags)}
        prev = []
        for t in tags:
            hit = next(r for r in stream if r["rate_tag"] == t and r["method"] == "mlp")
            prev.append(hit["prevalence"])
        ax1.plot(range(len(tags)), prev, "o-", color="#8E44AD", label="Empirical overlap prevalence")
        ax1.set_ylabel("Overlap prevalence")
        ax1.set_ylim(-0.02, 1.05)
        ax2 = ax1.twinx()
        for method, color in (("mlp", "#1F4E79"), ("retrigger", "#7F8C8D"), ("mlp_or_retrigger", "#000000")):
            ys = []
            for t in tags:
                hit = next(r for r in stream if r["rate_tag"] == t and r["method"] == method)
                ys.append(np.nan if hit.get("recall_unstable") else hit["recall"])
            ax2.plot(range(len(tags)), ys, "s--", color=color, label=f"{method} recall")
        ax2.set_ylabel("Recall (blank if fewer than 30 overlaps)")
        ax2.set_ylim(-0.02, 1.05)
        ax1.set_xticks(range(len(tags)), [t.replace("model_p_forward_", "p=").replace("measured_fe55_rate", "measured") for t in tags], rotation=20, ha="right", fontsize=8)
        ax1.set_title(f"Unconditional stream, Poisson model ({primary})")
        h1, l1 = ax1.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax1.legend(h1 + h2, l1 + l2, frameon=False, fontsize=7, loc="upper left")
        fig.tight_layout()
        p = out / "stream_prevalence_recall.png"
        fig.savefig(p, bbox_inches="tight")
        plt.close(fig)
        written.append(p.name)

    mae = [r for r in result["mae_rows"] if r["run_id"] == primary]
    if mae:
        fig, ax = plt.subplots(figsize=(6.8, 3.5), dpi=140)
        labels = [r["estimator"].replace("_", "\n") for r in mae]
        ax.bar(range(len(mae)), [r["mae_ch"] for r in mae], color="#1F4E79")
        ax.set_xticks(range(len(mae)), labels, fontsize=6)
        ax.set_ylabel("Isolated MAE (channels)")
        ax.set_title(f"Strict-split isolated height ({primary})")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()
        p = out / "strict_mae.png"
        fig.savefig(p, bbox_inches="tight")
        plt.close(fig)
        written.append(p.name)

    hard = [
        r
        for r in result["ratio_rows"]
        if r["run_id"] == primary and r["ratio"] == 0.25 and abs(r["gap_us"] - 0.4) < 1e-9
    ]
    if hard:
        fig, ax = plt.subplots(figsize=(6.4, 3.4), dpi=140)
        hard = sorted(hard, key=lambda r: r["method"])
        ax.bar(range(len(hard)), [r["f1"] for r in hard], color="#1F4E79")
        ax.set_xticks(range(len(hard)), [r["method"] for r in hard], rotation=20, ha="right", fontsize=8)
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("Balanced F1")
        ax.set_title("Hard cell A2/A1 = 0.25 at Δt = 0.4 µs")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()
        p = out / "hard_cell_0.25_0.4us.png"
        fig.savefig(p, bbox_inches="tight")
        plt.close(fig)
        written.append(p.name)
    return written


def _code_hashes() -> dict:
    names = [
        "sparse_pileup/segment_protocol.py",
        "sparse_pileup/strict_validation.py",
        "sparse_pileup/real_superpose.py",
        "sparse_pileup/ls_peak.py",
        "sparse_pileup/operating_region.py",
        "config/sdd_shape.json",
        "artifacts/v5_summary.json",
        "weights/dual_head.json",
    ]
    return {n: _sha256_text(ROOT / n) for n in names}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Segment-first constructed-pile-up validation")
    p.add_argument("--out", type=Path, default=ROOT / "artifacts" / "v6")
    args = p.parse_args(argv)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    print("Scanning recording buffers before any split fit or mix...", flush=True)
    campaign = scan_campaign(ROOT)
    rates = campaign_rates(campaign)
    print(
        f"  pulses={rates['n_pulses']} fe55={rates['n_fe55']} isolated={rates['n_isolated_fe55']} "
        f"fe55_rate={rates['rate_fe55_hz']:.1f} Hz cross_boundary_close={rates['n_cross_boundary_pairs_closer_than_8us']}",
        flush=True,
    )
    print("Replaying historical V5 test file...", flush=True)
    historical = _historical_block()
    off = historical["official_test_file"]
    print(
        f"  official file pile-up {off['n_pileup']} F1={off['f1']:.3f} isolated MAE={off['isolated_mae_ch']:.3f}",
        flush=True,
    )
    runs = []
    plan = [("blocked", 42, True), ("blocked", 43, False), ("blocked", 44, False),
            ("random", 42, False), ("random", 43, False), ("random", 44, False)]
    for mode, seed, full in plan:
        runs.append(run_one(campaign, mode, seed, full_maps=full))

    primary = next(r for r in runs if r["run_id"] == PRIMARY_RUN)
    gap_rows, ratio_rows, noise_rows, stream_rows, mae_rows, prev_rows, n8_rows = [], [], [], [], [], [], []
    run_summaries = []
    for r in runs:
        gap_rows.extend(r.pop("gap_rows"))
        ratio_rows.extend(r.pop("ratio_rows"))
        noise_rows.extend(r.pop("noise_rows"))
        stream_rows.extend(r.pop("stream_rows"))
        mae_rows.extend(r.pop("mae_rows"))
        prev_rows.extend(r.pop("prevalence_rows"))
        n8_rows.extend(r.pop("n8_rows"))
        run_summaries.append(r)

    blocked_ids = {r["run_id"] for r in run_summaries if r["mode"] == "blocked"}
    random_ids = {r["run_id"] for r in run_summaries if r["mode"] == "random"}
    agg = []
    agg += _aggregate(prev_rows, "blocked_init", blocked_ids, ["method", "study"])
    agg += _aggregate(prev_rows, "random_segment", random_ids, ["method", "study"])
    agg += _aggregate(gap_rows, "blocked_init", blocked_ids, ["method", "gap_us"])
    agg += _aggregate(gap_rows, "random_segment", random_ids, ["method", "gap_us"])
    agg += _aggregate(mae_rows, "blocked_init", blocked_ids, ["estimator"])
    agg += _aggregate(mae_rows, "random_segment", random_ids, ["estimator"])
    agg += _aggregate(
        [r for r in stream_rows if r.get("study") == "unconditional_stream"],
        "blocked_init",
        blocked_ids,
        ["method", "study", "label_rule", "rate_tag"],
    )
    agg += _aggregate(
        [r for r in stream_rows if r.get("study") == "unconditional_stream"],
        "random_segment",
        random_ids,
        ["method", "study", "label_rule", "rate_tag"],
    )
    agg += _aggregate(
        [r for r in ratio_rows if r.get("ratio") == 0.25],
        "blocked_init",
        blocked_ids,
        ["method", "gap_us", "ratio"],
    )
    agg += _aggregate(
        [r for r in ratio_rows if r.get("ratio") == 0.25],
        "random_segment",
        random_ids,
        ["method", "gap_us", "ratio"],
    )

    payload = {
        "protocol": PROTOCOL_PUBLIC,
        "command": "python -m sparse_pileup.strict_validation --out artifacts/v6",
        "python": sys.version,
        "numpy": np.__version__,
        "platform": platform.platform(),
        "epochs_published_constant": DEFAULT_EPOCHS,
        "code_sha256": _code_hashes(),
        "data_provenance": {
            "manifest_sha256": campaign.manifest_sha256,
            "metadata_sha256": campaign.metadata_sha256,
            "segment_sha256": {rec.index: rec.sha256 for rec in campaign.records},
            "rates": rates,
            "historical_pulse_split_leakage": historical_pulse_leakage(ROOT, DEFAULT_SEED),
        },
        "historical_reconciliation": historical,
        "runs": run_summaries,
        "primary_run_id": PRIMARY_RUN,
        "coincidence_samples": COINCIDENCE_SAMPLES,
        "limitations": [
            "Pile-up is linear superposition of measured isolated pulses, not a high-rate recording.",
            "Exponential inter-arrival times are a Poisson-process modelling assumption.",
            "No ballistic deficit, preamplifier reset, baseline wander, or analog dead time.",
            "The four-tap latch imposes a 1.3 us digital holdoff between accepted triggers.",
            "Snippet wings outside ± the footprint are treated as absent (truncation).",
            "Samples that exceed 0..4095 are clipped; ratio 4 cells can saturate.",
            "Three or more pulses inside 2 us are counted, not unfolded.",
            "A2/A1 outside about 0.80-1.25 scales a measured excess, including its noise, and is outside the Fe-55 amplitude-ratio range.",
            "Thresholds are frozen from the clean validation prevalence mix and are not retuned per cell, per noise level, or per rate.",
            "Recall is marked unstable when the positive count is below 30.",
        ],
    }
    # Attach flat tables for the plotter without putting waveforms in JSON.
    payload_for_plots = {
        "primary_run_id": PRIMARY_RUN,
        "gap_rows": gap_rows,
        "ratio_rows": ratio_rows,
        "stream_rows": stream_rows,
        "mae_rows": mae_rows,
    }
    (out / "summary.json").write_text(json.dumps(_jsonable(payload), indent=2), encoding="utf-8")
    _write_csv(out / "runs.csv", [
        {
            "run_id": r["run_id"],
            "mode": r["mode"],
            "seed": r["seed"],
            "n_train_segments": r["n_train_segments"],
            "n_val_segments": r["n_val_segments"],
            "n_test_segments": r["n_test_segments"],
            "n_train_snippets": r["n_train_snippets"],
            "n_val_snippets": r["n_val_snippets"],
            "n_test_snippets": r["n_test_snippets"],
            "tau_samples": r["template"]["tau_samples"],
            "pedestal_ch": r["template"]["pedestal_ch"],
            "baseline_sigma_ch": r["template"]["baseline_sigma_ch"],
            "train_amp_mean": r["amplitude_train"]["mean_ch"],
            "test_amp_mean": r["amplitude_test"]["mean_ch"],
            "mlp_threshold": r["thresholds"]["mlp"]["selected"],
            "test_n_pileup": r["test_n_pileup"],
        }
        for r in run_summaries
    ])
    mlp_by_run = {
        r["run_id"]: f"{float(r['thresholds']['mlp']['selected']):.2f}" for r in run_summaries
    }
    for table in (prev_rows, gap_rows, ratio_rows, noise_rows, stream_rows, n8_rows):
        annotate_threshold_metadata(table, mlp_by_run)
    _write_csv(out / "prevalence.csv", prev_rows)
    _write_csv(out / "mae.csv", mae_rows)
    _write_csv(out / "conditional_gap.csv", gap_rows)
    _write_csv(out / "conditional_ratio.csv", ratio_rows)
    _write_csv(out / "noise.csv", noise_rows)
    _write_csv(out / "stream.csv", stream_rows)
    _write_csv(out / "n8.csv", n8_rows)
    if not agg:
        raise RuntimeError("aggregate table is empty; refusing to write a blank file")
    _write_csv(out / "aggregate.csv", agg)
    figures = _plots(out, payload_for_plots)
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    summary["figures"] = figures
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {out}", flush=True)


if __name__ == "__main__":
    main()
