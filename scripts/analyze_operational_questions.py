"""Answer three descriptive questions using the reviewed 2024 model inputs.

Run: python scripts/analyze_operational_questions.py
Inputs remain unchanged. Outputs go to data/processed/analysis_questions and
images/analysis. No new downloads, model fitting or Power BI refresh is needed.
"""
from __future__ import annotations

import calendar
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUTPUT = PROCESSED / "analysis_questions"
IMAGES = ROOT / "images" / "analysis"
FACT_COLUMNS = [
    "pickup_hour", "PULocationID", "pickup_zone", "pickup_borough_grouped",
    "airport_pickup", "trip_count", "total_revenue",
]
TIME_COLUMNS = [
    "pickup_hour", "pickup_month", "pickup_dayofweek", "pickup_hour_num",
    "elapsed_hours",
]


def borough_comparison(fact: pd.DataFrame) -> pd.DataFrame:
    """Compare each borough's actual mix with its non-airport pickup subset."""
    borough = "pickup_borough_grouped"
    totals = fact.groupby(borough)[["trip_count", "total_revenue"]].sum()
    totals = totals.rename(columns={"trip_count": "trips", "total_revenue": "amount_usd"})
    for flag, prefix in [(0, "non_airport"), (1, "airport")]:
        part = fact.loc[fact.airport_pickup.eq(flag)].groupby(borough)[
            ["trip_count", "total_revenue"]
        ].sum()
        part = part.rename(columns={
            "trip_count": f"{prefix}_trips", "total_revenue": f"{prefix}_amount_usd"
        })
        totals = totals.join(part).fillna({
            f"{prefix}_trips": 0, f"{prefix}_amount_usd": 0
        })
        totals[f"{prefix}_mean_usd"] = (
            totals[f"{prefix}_amount_usd"] / totals[f"{prefix}_trips"].replace(0, np.nan)
        )
    totals["mean_usd"] = totals.amount_usd / totals.trips
    totals["airport_trip_share"] = totals.airport_trips / totals.trips
    return totals.reset_index()


def monthly_comparison(hourly: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Give each month the same annual weekday mix, using real-hour rates."""
    by_day = hourly.groupby(["pickup_month", "pickup_dayofweek"])[
        ["trip_count", "elapsed_hours"]
    ].sum()
    by_day["trips_per_hour"] = by_day.trip_count / by_day.elapsed_hours
    weights = hourly.groupby("pickup_dayofweek").elapsed_hours.sum()
    weights = weights / weights.sum()
    rate_grid = by_day.trips_per_hour.unstack()
    if rate_grid.isna().any().any():
        raise ValueError("Each month must have observations for every weekday in the reference mix")
    monthly = hourly.groupby("pickup_month")[["trip_count", "elapsed_hours"]].sum()
    monthly["observed_trips_per_hour"] = monthly.trip_count / monthly.elapsed_hours
    monthly["standardized_trips_per_hour"] = rate_grid.mul(weights, axis=1).sum(axis=1)
    monthly["observed_rank"] = monthly.observed_trips_per_hour.rank(ascending=False, method="min").astype(int)
    monthly["standardized_rank"] = monthly.standardized_trips_per_hour.rank(ascending=False, method="min").astype(int)
    by_day["reference_weekday_weight"] = by_day.index.get_level_values("pickup_dayofweek").map(weights)
    return monthly.reset_index(), by_day.reset_index()


def window_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    """Pickup-clock windows; weekend nights continue into the following day."""
    weekday, hour = frame.pickup_dayofweek, frame.pickup_hour_num
    return {
        "Weekday mornings": weekday.lt(5) & hour.between(7, 9),
        "Weekend nights": (
            weekday.isin([4, 5]) & hour.between(20, 23)
        ) | (
            weekday.isin([5, 6]) & hour.between(0, 2)
        ),
    }


def zone_comparison(fact: pd.DataFrame, hours: pd.DataFrame) -> pd.DataFrame:
    """Keep all zones, with one shared period-hour denominator per window."""
    periods = window_masks(hours)
    parts = []
    for name, mask in window_masks(fact).items():
        zones = fact.loc[mask].groupby(["PULocationID", "pickup_zone"])[
            ["trip_count", "total_revenue"]
        ].sum().reset_index()
        zones = zones.sort_values(["trip_count", "PULocationID"], ascending=[False, True])
        zones["window"] = name
        zones["rank"] = np.arange(1, len(zones) + 1)
        zones["window_trips"] = zones.trip_count.sum()
        zones["window_hours"] = hours.loc[periods[name], "elapsed_hours"].sum()
        zones["trip_share"] = zones.trip_count / zones.window_trips
        zones["trips_per_hour"] = zones.trip_count / zones.window_hours
        parts.append(zones)
    return pd.concat(parts, ignore_index=True)


def save_charts(boroughs: pd.DataFrame, months: pd.DataFrame, zones: pd.DataFrame) -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.titlelocation": "left", "axes.titlesize": 16,
        "savefig.facecolor": "white",
    })
    blue, gold = "#2F80ED", "#D99100"
    main = boroughs.set_index("pickup_borough_grouped").loc[
        ["Manhattan", "Brooklyn", "Bronx", "Queens"]
    ]
    fig, ax = plt.subplots(figsize=(11, 5.5))
    y = np.arange(len(main))
    ax.barh(y - .18, main.mean_usd, height=.32, color=blue, label="All pickups")
    ax.barh(y + .18, main.non_airport_mean_usd, height=.32, color=gold, label="Airport pickups excluded")
    for positions, values in [(y - .18, main.mean_usd), (y + .18, main.non_airport_mean_usd)]:
        for position, value in zip(positions, values):
            ax.text(value + .8, position, f"${value:.2f}", va="center", fontsize=10)
    ax.set(yticks=y, yticklabels=main.index, xlabel="Mean recorded amount per trip (USD)", xlim=(0, 88))
    ax.invert_yaxis()
    ax.set_title("Queens remains higher when airport pickups are excluded", pad=18)
    ax.legend(loc="lower right", frameon=False)
    fig.text(.02, .02, "2024 retained yellow taxi trips. NYC boroughs with at least 5,000 trips. Pickup zones define airports.", fontsize=9, color="#555555")
    fig.tight_layout(rect=(0, .06, 1, 1))
    fig.savefig(IMAGES / "06_airport_mix.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(months.pickup_month, months.observed_trips_per_hour, "o-", color=blue, label="Observed hourly rate")
    ax.plot(months.pickup_month, months.standardized_trips_per_hour, "s--", color=gold, label="Same weekday mix")
    ax.set(xticks=range(1, 13), xticklabels=list(calendar.month_abbr)[1:], ylabel="Trips per real hour", ylim=(0, 5500))
    ax.set_title("October remains first after adjusting the weekday mix", pad=18)
    ax.grid(axis="y", alpha=.2)
    ax.legend(loc="lower right", frameon=False)
    fig.text(.02, .02, "Each month uses the 2024 weekday-hour weights. This does not adjust for holidays, weather or taxi supply.", fontsize=9, color="#555555")
    fig.tight_layout(rect=(0, .06, 1, 1))
    fig.savefig(IMAGES / "07_calendar_comparison.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(16, 6.6), sharex=True)
    for ax, name, color in zip(axes, ["Weekday mornings", "Weekend nights"], [blue, gold]):
        top = zones.loc[zones.window.eq(name)].head(10)
        ax.barh(top.pickup_zone, top.trip_share * 100, color=color)
        ax.invert_yaxis()
        ax.set_title(name, pad=15)
        ax.set_xlabel("Share of trips within this time window (%)")
        ax.set_xlim(0, 8)
        for i, value in enumerate(top.trip_share * 100):
            ax.text(value + .08, i, f"{value:.1f}%", va="center", fontsize=10)
    fig.suptitle("Annual zone rankings conceal different morning and night patterns", x=.025, ha="left", fontsize=17)
    fig.text(.025, .025, "Mornings: Mon-Fri 07:00-09:59. Nights: Friday and Saturday 20:00-02:59 the following day. Trip purpose is unknown.", fontsize=10, color="#555555")
    fig.tight_layout(rect=(0, .06, 1, .93), w_pad=3)
    fig.savefig(IMAGES / "08_zone_time_windows.png", dpi=160)
    plt.close(fig)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    IMAGES.mkdir(parents=True, exist_ok=True)
    fact_path = PROCESSED / "taxi_analysis_2024_final.csv"
    hour_path = PROCESSED / "dim_hour_2024.csv"
    fact = pd.read_csv(fact_path, usecols=FACT_COLUMNS, parse_dates=["pickup_hour"])
    hours = pd.read_csv(hour_path, usecols=TIME_COLUMNS, parse_dates=["pickup_hour"])
    fact = fact.merge(hours.drop(columns="elapsed_hours"), on="pickup_hour", how="left", validate="many_to_one", indicator=True)
    if not fact.pop("_merge").eq("both").all():
        raise ValueError("Fact hours missing from the reviewed calendar")
    expected = json.loads((PROCESSED / "validation_summary.json").read_text(encoding="utf-8"))
    assert fact.trip_count.sum() == expected["clean_trips"]
    assert abs(fact.total_revenue.sum() - expected["recorded_total_usd"]) < .01
    assert hours.elapsed_hours.sum() == expected["real_hours"]
    hourly = hours.merge(fact.groupby("pickup_hour").trip_count.sum(), on="pickup_hour", how="left", validate="one_to_one")
    hourly["trip_count"] = hourly.trip_count.fillna(0)
    boroughs = borough_comparison(fact)
    months, weekday_rates = monthly_comparison(hourly)
    zones = zone_comparison(fact, hours)
    for name, table in [("borough_airport_mix", boroughs), ("monthly_calendar_comparison", months), ("monthly_weekday_rates", weekday_rates), ("zone_time_windows", zones)]:
        table.to_csv(OUTPUT / f"{name}.csv", index=False, float_format="%.10f")
    queens = boroughs.set_index("pickup_borough_grouped").loc["Queens"]
    manhattan = boroughs.set_index("pickup_borough_grouped").loc["Manhattan"]
    october = months.set_index("pickup_month").loc[10]
    september = months.set_index("pickup_month").loc[9]
    morning_top = zones.loc[zones.window.eq("Weekday mornings")].head(10)
    night_top = zones.loc[zones.window.eq("Weekend nights")].head(10)
    overlap = morning_top.loc[morning_top.PULocationID.isin(night_top.PULocationID), "pickup_zone"].tolist()
    summary = {
        "source_sha256": {p.name: hashlib.file_digest(p.open("rb"), "sha256").hexdigest() for p in [fact_path, hour_path]},
        "total_trips": int(fact.trip_count.sum()),
        "queens_all_mean_usd": float(queens.mean_usd),
        "queens_non_airport_mean_usd": float(queens.non_airport_mean_usd),
        "queens_airport_trip_share": float(queens.airport_trip_share),
        "manhattan_mean_usd": float(manhattan.mean_usd),
        "queens_manhattan_gap_reduction_fraction": float(1 - (queens.non_airport_mean_usd - manhattan.mean_usd) / (queens.mean_usd - manhattan.mean_usd)),
        "october_observed_trips_per_hour": float(october.observed_trips_per_hour),
        "october_standardized_trips_per_hour": float(october.standardized_trips_per_hour),
        "october_standardized_rank": int(october.standardized_rank),
        "october_vs_september_standardized_fraction": float(october.standardized_trips_per_hour / september.standardized_trips_per_hour - 1),
        "top_10_zone_overlap": overlap,
        "window_definitions": {"Weekday mornings": "Mon-Fri 07:00-09:59", "Weekend nights": "Friday and Saturday 20:00-02:59 the following day"},
    }
    (OUTPUT / "findings.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    save_charts(boroughs, months, zones)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
