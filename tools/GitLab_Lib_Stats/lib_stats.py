#!/usr/bin/env python3
import argparse
import csv
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone

import gitlab

# How it works:
# First, all merge requests for the given project are fetched from GitLab using the GitLab API.
# The fetched merge requests are then filtered based on their creation or merge dates to fit specific time ranges
#   (e.g., last year, last month).
# From these filtered lists, various statistics are computed,
#   such as total number of MRs, average time to merge, etc.
# These statistics are then printed to the console and are also exported to CSV files for further analysis.

# TODO / Idea list:
# * Add issue stats
# * Add Plotting of stats over time (e.g. monthly), possible with externally processing the CSV files
# * Filter and Analytics for Authors and Mergers
# * Automatically generate a report (Markdown or PDF[preferred]) with the statistics and charts
# * Create Pipeline to run this periodically and update stats
# * Add to short summery Merged new vs total merged in last 30 days
# * Split into multiple files and make some classes
# * Differentiation between Major and Minor repository's
#

# Project IDs:
id_SymLibs = str(21545491)
id_FPLibs = str(21601606)
id_Package3D = str(21604637)
id_FP3dGen = str(21610360)
id_Templates = str(21506275)
id_3dSources = str(21508935)
id_KLC = str(23412843)
id_KLU = str(21511814)

project_ids = {
    "Symbols": id_SymLibs,
    "Footprints": id_FPLibs,
    "Packages_3D": id_Package3D,
    "Footprint_and_3D_model_Generator": id_FP3dGen,
    "Templates": id_Templates,
    "Packages3D_source": id_3dSources,
    "KiCad_Library_Conventions": id_KLC,
    "KiCAD_Library_utilities": id_KLU,
}


#
# Helper functions
#
def iso_date(dt: datetime):
    """Convert a datetime to GitLab ISO 8601 format (UTC, 'Z' suffix)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parseUtcTime(created_at_str):
    """Parse GitLab time strings ending with 'Z' into an aware UTC datetime.

    Handles both fractional seconds and whole-second timestamps.
    """
    # Expect formats like: 2024-11-01T12:34:56.123Z or 2024-11-01T12:34:56Z
    try:
        dt = datetime.strptime(created_at_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        dt = datetime.strptime(created_at_str, "%Y-%m-%dT%H:%M:%SZ")
    return dt.replace(tzinfo=timezone.utc)


def averageTimeFromSeconds(seconds_list):
    """Return average of a list of seconds (0 if list empty)."""
    if not seconds_list:
        return 0
    return sum(seconds_list) / len(seconds_list)


def medianTimeFromSeconds(seconds_list):
    """Return median of a list of seconds (0 if list empty)."""
    if not seconds_list:
        return 0
    return statistics.median(seconds_list)


def maxTimeFromSeconds(seconds_list):
    """Return maximum seconds (0 if list empty)."""
    if not seconds_list:
        return 0
    return max(seconds_list)


def minTimeFromSeconds(seconds_list):
    """Return minimum seconds (0 if list empty)."""
    if not seconds_list:
        return 0
    return min(seconds_list)


def stdDevPopulationTimeFromSeconds(seconds_list):
    """Return population standard deviation of seconds (0 if list empty)."""
    if not seconds_list:
        return 0
    return statistics.pstdev(seconds_list)


def stdDevSampleTimeFromSeconds(seconds_list):
    """Return sample standard deviation of seconds (0 if list empty or has less then 2 entries)."""
    if not seconds_list or len(seconds_list) < 2:
        return 0
    return statistics.stdev(seconds_list)


def secondsToHMS(seconds):
    """Convert seconds to d HH:MM:SS."""
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return "0d 00:00:00"

    if total < 0:
        return "0d 00:00:00"

    days = total // 86400
    rem = total % 86400
    hours = rem // 3600
    rem = rem % 3600
    minutes = rem // 60
    secs = rem % 60
    return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"


#
# GitLab API functions using python-gitlab
#


def getMergeRequests(project_id, token, created_after=None, created_before=None):
    """Fetch merge requests from GitLab for a given project ID."""
    gl = gitlab.Gitlab("https://gitlab.com", private_token=token, timeout=10)
    if len(token) > 0:
        gl.auth()

    project = gl.projects.get(project_id)

    # Verwende iterator=True um große Resultate seitenweise zu holen
    params = {
        "state": "all",
        "order_by": "created_at",
        "sort": "asc",
        "per_page": 100,
    }  # desc
    if created_after:
        params["created_after"] = created_after
    if created_before:
        params["created_before"] = created_before

    merge_requests = []

    while True:
        try:
            merge_requests = [
                mr
                for mr in project.mergerequests.list(
                    iterator=True, **params, timeout=30.0
                )
            ]
            break
        except gitlab.exceptions.GitlabGetError as e:
            print("Error getting merge requests:", str(e), file=sys.stderr)
    return merge_requests


#
# Export Functions
#


def exportMergeRequestsToCSV(merge_requests, filename):
    """Export a list of merge requests to a CSV file."""

    with open(filename, mode="w", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "IID",
            "Title",
            "State",
            "Author",
            "Created At",
            "Merged At",
            "URL",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for mr in merge_requests:
            writer.writerow(
                {
                    "IID": mr.iid,
                    "Title": mr.title,
                    "State": mr.state,
                    "Author": getattr(mr, "author", {}).get("username", "n/a"),
                    "Created At": mr.created_at,
                    "Merged At": getattr(mr, "merged_at", "n/a"),
                    "URL": mr.web_url,
                }
            )


#
# Filter Functions
#


# Filters based on created_at
def filterMergeRequestsByCreatedAtYear(merge_requests, year):
    """Filter MRs by created_at year."""
    filtered_mrs = []
    for mr in merge_requests:
        created_at = parseUtcTime(mr.created_at)
        if created_at.year == year:
            filtered_mrs.append(mr)
    return filtered_mrs


def filterMergeRequestsByCreatedAtMonth(merge_requests, year, month):
    """Filter MRs by created_at year and month."""
    filtered_mrs = []
    for mr in merge_requests:
        created_at = parseUtcTime(mr.created_at)
        if created_at.year == year and created_at.month == month:
            filtered_mrs.append(mr)
    return filtered_mrs


def filterMergeRequestsByCreatedAtTimeRange(merge_requests, start_date, end_date):
    """Filter MRs by created_at time range."""
    filtered_mrs = []
    for mr in merge_requests:
        created_at = parseUtcTime(mr.created_at)
        if start_date <= created_at <= end_date:
            filtered_mrs.append(mr)
    return filtered_mrs


# Filters based on merged_at (only include MRs where merged_at is set)
def filterMergeRequestsByMergedAtYear(merge_requests, year):
    """Filter MRs by merged_at year."""
    filtered_mrs = []
    for mr in merge_requests:
        if getattr(mr, "merged_at", None) is None:
            continue
        merged_at = parseUtcTime(mr.merged_at)
        if merged_at.year == year:
            filtered_mrs.append(mr)
    return filtered_mrs


def filterMergeRequestsByMergedAtMonth(merge_requests, year, month):
    """Filter MRs by merged_at year and month."""
    filtered_mrs = []
    for mr in merge_requests:
        if getattr(mr, "merged_at", None) is None:
            continue
        merged_at = parseUtcTime(mr.merged_at)
        if merged_at.year == year and merged_at.month == month:
            filtered_mrs.append(mr)
    return filtered_mrs


def filterMergeRequestsByMergedAtTimeRange(merge_requests, start_date, end_date):
    """Filter MRs by merged_at time range."""
    filtered_mrs = []
    for mr in merge_requests:
        if getattr(mr, "merged_at", None) is None:
            continue
        merged_at = parseUtcTime(mr.merged_at)
        if start_date <= merged_at <= end_date:
            filtered_mrs.append(mr)
    return filtered_mrs


# Filters based on closed_at (only include MRs where closed_at is set)
def filterMergeRequestsByClosedAtYear(merge_requests, year):
    """Filter MRs by closed_at year."""
    filtered_mrs = []
    for mr in merge_requests:
        if getattr(mr, "closed_at", None) is None:
            continue
        closed_at = parseUtcTime(mr.closed_at)
        if closed_at.year == year:
            filtered_mrs.append(mr)
    return filtered_mrs


def filterMergeRequestsByClosedAtMonth(merge_requests, year, month):
    """Filter MRs by closed_at year and month."""
    filtered_mrs = []
    for mr in merge_requests:
        if getattr(mr, "closed_at", None) is None:
            continue
        closed_at = parseUtcTime(mr.closed_at)
        if closed_at.year == year and closed_at.month == month:
            filtered_mrs.append(mr)
    return filtered_mrs


def filterMergeRequestsByClosedAtTimeRange(merge_requests, start_date, end_date):
    """Filter MRs by closed_at time range."""
    filtered_mrs = []
    for mr in merge_requests:
        if getattr(mr, "closed_at", None) is None:
            continue
        closed_at = parseUtcTime(mr.closed_at)
        if start_date <= closed_at <= end_date:
            filtered_mrs.append(mr)
    return filtered_mrs


# Filters open MRs
def filterMergeRequestsOpenFinished(merge_requests):
    """Filter MRs into open, finished, merged, and closed lists."""
    filtered_open_mrs = []
    filtered_finished_mrs = []
    filtered_merged_mrs = []
    filtered_closed_mrs = []
    for mr in merge_requests:
        if getattr(mr, "state", None) is None:
            continue
        state = mr.state
        if state == "opened":
            filtered_open_mrs.append(mr)
        else:
            filtered_finished_mrs.append(mr)

        if state == "merged":
            filtered_merged_mrs.append(mr)

        if state == "closed":
            filtered_closed_mrs.append(mr)
    return (
        filtered_open_mrs,
        filtered_finished_mrs,
        filtered_merged_mrs,
        filtered_closed_mrs,
    )


#
# Statistics Functions
#


# This creates a summary of merge request statistics for a list of merge requests
def mergeRequestStats(merge_requests):
    """Compute statistics for a list of merge requests."""
    stats = {
        "total": len(merge_requests),
        "merged": 0,
        "open": 0,
        "closed": 0,
        "finished": 0,
        "percentageMerged": 0,
        "percentageClosed": 0,
        "percentageFinished": 0,
        # Statistics on time to merge
        "avgTimeToMergeSeconds": 0,
        "avgTimeToMergeDHMS": "",
        "medianTimeToMergeSeconds": 0,
        "medianTimeToMergeDHMS": "",
        "maxTimeToMergeSeconds": 0,
        "maxTimeToMergeDHMS": "",
        "minTimeToMergeSeconds": 0,
        "minTimeToMergeDHMS": "",
        "stdDevPopulationTimeToMergeSeconds": 0,
        "stdDevPopulationTimeToMergeDHMS": "",
        "stdDevSampleTimeToMergeSeconds": 0,
        "stdDevSampleTimeToMergeDHMS": "",
        # Statistics on time to close
        "avgTimeToCloseSeconds": 0,
        "avgTimeToCloseDHMS": "",
        "medianTimeToCloseSeconds": 0,
        "medianTimeToCloseDHMS": "",
        "maxTimeToCloseSeconds": 0,
        "maxTimeToCloseDHMS": "",
        "minTimeToCloseSeconds": 0,
        "minTimeToCloseDHMS": "",
        "stdDevPopulationTimeToCloseSeconds": 0,
        "stdDevPopulationTimeToCloseDHMS": "",
        "stdDevSampleTimeToClosedSeconds": 0,
        "stdDevSampleTimeToCloseDHMS": "",
    }

    timeToMergeSeconds = []
    timeToCloseSeconds = []

    for mr in merge_requests:
        state = mr.state
        if state == "merged":
            stats["merged"] += 1
            stats["finished"] += 1
            if mr.merged_at is not None and mr.created_at is not None:
                timeToMergeSeconds.append(
                    (
                        parseUtcTime(mr.merged_at) - parseUtcTime(mr.created_at)
                    ).total_seconds()
                )
        elif state == "opened":
            stats["open"] += 1
        elif state == "closed":
            stats["closed"] += 1
            stats["finished"] += 1
            if mr.closed_at is not None and mr.created_at is not None:
                timeToCloseSeconds.append(
                    (
                        parseUtcTime(mr.closed_at) - parseUtcTime(mr.created_at)
                    ).total_seconds()
                )

    if stats["total"] > 0:
        percentage_merged = (stats["merged"] / stats["total"]) * 100
        stats["percentageMerged"] = percentage_merged
        percentage_closed = (stats["closed"] / stats["total"]) * 100
        stats["percentageClosed"] = percentage_closed
        percentage_finished = (
            (stats["merged"] + stats["closed"]) / stats["total"]
        ) * 100
        stats["percentageFinished"] = percentage_finished

    if len(timeToMergeSeconds) > 0:
        stats["avgTimeToMergeSeconds"] = averageTimeFromSeconds(timeToMergeSeconds)
        stats["avgTimeToMergeDHMS"] = secondsToHMS(stats["avgTimeToMergeSeconds"])
        stats["medianTimeToMergeSeconds"] = medianTimeFromSeconds(timeToMergeSeconds)
        stats["medianTimeToMergeDHMS"] = secondsToHMS(stats["medianTimeToMergeSeconds"])
        stats["maxTimeToMergeSeconds"] = maxTimeFromSeconds(timeToMergeSeconds)
        stats["maxTimeToMergeDHMS"] = secondsToHMS(stats["maxTimeToMergeSeconds"])
        stats["minTimeToMergeSeconds"] = minTimeFromSeconds(timeToMergeSeconds)
        stats["minTimeToMergeDHMS"] = secondsToHMS(stats["minTimeToMergeSeconds"])
        stats["stdDevPopulationTimeToMergeSeconds"] = stdDevPopulationTimeFromSeconds(
            timeToMergeSeconds
        )
        stats["stdDevPopulationTimeToMergeDHMS"] = secondsToHMS(
            stats["stdDevPopulationTimeToMergeSeconds"]
        )
        stats["stdDevSampleTimeToMergeSeconds"] = stdDevSampleTimeFromSeconds(
            timeToMergeSeconds
        )
        stats["stdDevSampleTimeToMergeDHMS"] = secondsToHMS(
            stats["stdDevSampleTimeToMergeSeconds"]
        )

    if len(timeToCloseSeconds) > 0:
        stats["avgTimeToCloseSeconds"] = averageTimeFromSeconds(timeToCloseSeconds)
        stats["avgTimeToCloseDHMS"] = secondsToHMS(stats["avgTimeToCloseSeconds"])
        stats["medianTimeToCloseSeconds"] = medianTimeFromSeconds(timeToCloseSeconds)
        stats["medianTimeToCloseDHMS"] = secondsToHMS(stats["medianTimeToCloseSeconds"])
        stats["maxTimeToCloseSeconds"] = maxTimeFromSeconds(timeToCloseSeconds)
        stats["maxTimeToCloseDHMS"] = secondsToHMS(stats["maxTimeToCloseSeconds"])
        stats["minTimeToCloseSeconds"] = minTimeFromSeconds(timeToCloseSeconds)
        stats["minTimeToCloseDHMS"] = secondsToHMS(stats["minTimeToCloseSeconds"])
        stats["stdDevPopulationTimeToCloseSeconds"] = stdDevPopulationTimeFromSeconds(
            timeToCloseSeconds
        )
        stats["stdDevPopulationTimeToCloseDHMS"] = secondsToHMS(
            stats["stdDevPopulationTimeToCloseSeconds"]
        )
        stats["stdDevSampleTimeToCloseSeconds"] = stdDevSampleTimeFromSeconds(
            timeToCloseSeconds
        )
        stats["stdDevSampleTimeToCloseDHMS"] = secondsToHMS(
            stats["stdDevSampleTimeToCloseSeconds"]
        )

    return stats


#
# Summary Functions
#


def summaryCSVMergeRequestsByCreatedAtMonthly(
    merge_requests, project_name, max_consecutive_empty=1, incluede_current_month=False
):
    """Group MR stats by month, iterating backwards from the current month.

    Stops when `max_consecutive_empty` consecutive months contain no MRs.
    """
    statList = []

    now = datetime.now(timezone.utc)
    year = now.year
    if incluede_current_month:
        month = now.month  # Start from current month
    else:
        month = now.month - 1  # Start from previous month
        if month == 0:
            month = 12
            year -= 1

    consecutive_empty = 0

    # Iterate month-by-month backwards until threshold of consecutive empty months reached
    while True:
        filtered_mrs = filterMergeRequestsByCreatedAtMonth(merge_requests, year, month)

        if not filtered_mrs:
            consecutive_empty += 1
        else:
            consecutive_empty = 0
            stats = mergeRequestStats(filtered_mrs)
            stats["year"] = year
            stats["month"] = month
            statList.append(stats)

        if consecutive_empty >= max_consecutive_empty:
            break

        # Move to previous month
        month -= 1
        if month == 0:
            month = 12
            year -= 1

        # Safety: stop if we go too far back (arbitrary cutoff year)
        if year < 2000:
            break

    print(len(statList), "monthly stats found.")

    with open(
        f"./{project_name}/mrStatsGroupedByCreatedAtMonthly.csv",
        mode="w",
        newline="",
        encoding="utf-8",
    ) as csvfile:

        fieldnames = [
            "year",
            "month",
            "total",
            "merged",
            "open",
            "closed",
            "finished",
            "percentageMerged",
            "percentageClosed",
            "percentageFinished",
            "avgTimeToMergeSeconds",
            "avgTimeToMergeDHMS",
            "medianTimeToMergeSeconds",
            "medianTimeToMergeDHMS",
            "maxTimeToMergeSeconds",
            "maxTimeToMergeDHMS",
            "minTimeToMergeSeconds",
            "minTimeToMergeDHMS",
            "stdDevPopulationTimeToMergeSeconds",
            "stdDevPopulationTimeToMergeDHMS",
            "stdDevSampleTimeToMergeSeconds",
            "stdDevSampleTimeToMergeDHMS",
            "avgTimeToCloseSeconds",
            "avgTimeToCloseDHMS",
            "medianTimeToCloseSeconds",
            "medianTimeToCloseDHMS",
            "maxTimeToCloseSeconds",
            "maxTimeToCloseDHMS",
            "minTimeToCloseSeconds",
            "minTimeToCloseDHMS",
            "stdDevPopulationTimeToCloseSeconds",
            "stdDevPopulationTimeToCloseDHMS",
            "stdDevSampleTimeToCloseSeconds",
            "stdDevSampleTimeToCloseDHMS",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()

        for stat in statList:
            writer.writerow(
                {
                    "year": stat["year"],
                    "month": stat["month"],
                    "total": stat["total"],
                    "merged": stat["merged"],
                    "open": stat["open"],
                    "closed": stat["closed"],
                    "finished": stat["finished"],
                    "percentageMerged": stat["percentageMerged"],
                    "percentageClosed": stat["percentageClosed"],
                    "percentageFinished": stat["percentageFinished"],
                    "avgTimeToMergeSeconds": stat["avgTimeToMergeSeconds"],
                    "avgTimeToMergeDHMS": stat["avgTimeToMergeDHMS"],
                    "medianTimeToMergeSeconds": stat["medianTimeToMergeSeconds"],
                    "medianTimeToMergeDHMS": stat["medianTimeToMergeDHMS"],
                    "maxTimeToMergeSeconds": stat["maxTimeToMergeSeconds"],
                    "maxTimeToMergeDHMS": stat["maxTimeToMergeDHMS"],
                    "minTimeToMergeSeconds": stat["minTimeToMergeSeconds"],
                    "minTimeToMergeDHMS": stat["minTimeToMergeDHMS"],
                    "stdDevPopulationTimeToMergeSeconds": stat[
                        "stdDevPopulationTimeToMergeSeconds"
                    ],
                    "stdDevPopulationTimeToMergeDHMS": stat[
                        "stdDevPopulationTimeToMergeDHMS"
                    ],
                    "stdDevSampleTimeToMergeSeconds": stat[
                        "stdDevSampleTimeToMergeSeconds"
                    ],
                    "stdDevSampleTimeToMergeDHMS": stat["stdDevSampleTimeToMergeDHMS"],
                    "avgTimeToCloseSeconds": stat["avgTimeToCloseSeconds"],
                    "avgTimeToCloseDHMS": stat["avgTimeToCloseDHMS"],
                    "medianTimeToCloseSeconds": stat["medianTimeToCloseSeconds"],
                    "medianTimeToCloseDHMS": stat["medianTimeToCloseDHMS"],
                    "maxTimeToCloseSeconds": stat["maxTimeToCloseSeconds"],
                    "maxTimeToCloseDHMS": stat["maxTimeToCloseDHMS"],
                    "minTimeToCloseSeconds": stat["minTimeToCloseSeconds"],
                    "minTimeToCloseDHMS": stat["minTimeToCloseDHMS"],
                    "stdDevPopulationTimeToCloseSeconds": stat[
                        "stdDevPopulationTimeToCloseSeconds"
                    ],
                    "stdDevPopulationTimeToCloseDHMS": stat[
                        "stdDevPopulationTimeToCloseDHMS"
                    ],
                    "stdDevSampleTimeToCloseSeconds": stat[
                        "stdDevSampleTimeToMergeSeconds"
                    ],
                    "stdDevSampleTimeToCloseDHMS": stat["stdDevSampleTimeToCloseDHMS"],
                }
            )

    return statList


def summaryCSVMergeRequestsByCreatedAtYearly(
    merge_requests, project_name, max_consecutive_empty=1, incluede_current_year=False
):
    """Group MR stats by year, iterating backwards from the previous year.

    Stops when `max_consecutive_empty` consecutive years contain no MRs.
    Writes `mrStatsGroupedByCreatedAtYearly.csv`.
    """
    statList = []

    now = datetime.now(timezone.utc)
    if incluede_current_year:
        year = now.year  # start from the current year
    else:
        year = now.year - 1  # start from the previous year

    consecutive_empty = 0

    while True:
        filtered_mrs = filterMergeRequestsByCreatedAtYear(merge_requests, year)

        if not filtered_mrs:
            consecutive_empty += 1
        else:
            consecutive_empty = 0
            stats = mergeRequestStats(filtered_mrs)
            stats["year"] = year
            statList.append(stats)

        if consecutive_empty >= max_consecutive_empty:
            break

        year -= 1
        # Safety: stop if we go too far back (arbitrary cutoff year)
        if year < 2000:
            break

    print(len(statList), "yearly stats found.")

    with open(
        f"./{project_name}/mrStatsGroupedByCreatedAtYearly.csv",
        mode="w",
        newline="",
        encoding="utf-8",
    ) as csvfile:
        fieldnames = [
            "year",
            "total",
            "merged",
            "open",
            "closed",
            "finished",
            "percentageMerged",
            "percentageClosed",
            "percentageFinished",
            "avgTimeToMergeSeconds",
            "avgTimeToMergeDHMS",
            "medianTimeToMergeSeconds",
            "medianTimeToMergeDHMS",
            "maxTimeToMergeSeconds",
            "maxTimeToMergeDHMS",
            "minTimeToMergeSeconds",
            "minTimeToMergeDHMS",
            "stdDevPopulationTimeToMergeSeconds",
            "stdDevPopulationTimeToMergeDHMS",
            "stdDevSampleTimeToMergeSeconds",
            "stdDevSampleTimeToMergeDHMS",
            "avgTimeToCloseSeconds",
            "avgTimeToCloseDHMS",
            "medianTimeToCloseSeconds",
            "medianTimeToCloseDHMS",
            "maxTimeToCloseSeconds",
            "maxTimeToCloseDHMS",
            "minTimeToCloseSeconds",
            "minTimeToCloseDHMS",
            "stdDevPopulationTimeToCloseSeconds",
            "stdDevPopulationTimeToCloseDHMS",
            "stdDevSampleTimeToCloseSeconds",
            "stdDevSampleTimeToCloseDHMS",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()

        for stat in statList:
            writer.writerow(
                {
                    "year": stat["year"],
                    "total": stat["total"],
                    "merged": stat["merged"],
                    "open": stat["open"],
                    "closed": stat["closed"],
                    "finished": stat["finished"],
                    "percentageMerged": stat["percentageMerged"],
                    "percentageClosed": stat["percentageClosed"],
                    "percentageFinished": stat["percentageFinished"],
                    "avgTimeToMergeSeconds": stat["avgTimeToMergeSeconds"],
                    "avgTimeToMergeDHMS": stat["avgTimeToMergeDHMS"],
                    "medianTimeToMergeSeconds": stat["medianTimeToMergeSeconds"],
                    "medianTimeToMergeDHMS": stat["medianTimeToMergeDHMS"],
                    "maxTimeToMergeSeconds": stat["maxTimeToMergeSeconds"],
                    "maxTimeToMergeDHMS": stat["maxTimeToMergeDHMS"],
                    "minTimeToMergeSeconds": stat["minTimeToMergeSeconds"],
                    "minTimeToMergeDHMS": stat["minTimeToMergeDHMS"],
                    "stdDevPopulationTimeToMergeSeconds": stat[
                        "stdDevPopulationTimeToMergeSeconds"
                    ],
                    "stdDevPopulationTimeToMergeDHMS": stat[
                        "stdDevPopulationTimeToMergeDHMS"
                    ],
                    "stdDevSampleTimeToMergeSeconds": stat[
                        "stdDevSampleTimeToMergeSeconds"
                    ],
                    "stdDevSampleTimeToMergeDHMS": stat["stdDevSampleTimeToMergeDHMS"],
                    "avgTimeToCloseSeconds": stat["avgTimeToCloseSeconds"],
                    "avgTimeToCloseDHMS": stat["avgTimeToCloseDHMS"],
                    "medianTimeToCloseSeconds": stat["medianTimeToCloseSeconds"],
                    "medianTimeToCloseDHMS": stat["medianTimeToCloseDHMS"],
                    "maxTimeToCloseSeconds": stat["maxTimeToCloseSeconds"],
                    "maxTimeToCloseDHMS": stat["maxTimeToCloseDHMS"],
                    "minTimeToCloseSeconds": stat["minTimeToCloseSeconds"],
                    "minTimeToCloseDHMS": stat["minTimeToCloseDHMS"],
                    "stdDevPopulationTimeToCloseSeconds": stat[
                        "stdDevPopulationTimeToCloseSeconds"
                    ],
                    "stdDevPopulationTimeToCloseDHMS": stat[
                        "stdDevPopulationTimeToCloseDHMS"
                    ],
                    "stdDevSampleTimeToCloseSeconds": stat[
                        "stdDevSampleTimeToMergeSeconds"
                    ],
                    "stdDevSampleTimeToCloseDHMS": stat["stdDevSampleTimeToCloseDHMS"],
                }
            )

    return statList


def summaryCSVMergeRequestsByMergedAtMonthly(
    merge_requests, project_name, max_consecutive_empty=1, incluede_current_month=False
):
    """Summary grouped by the MR `merged_at` month. Stops after `max_consecutive_empty` empty months."""
    statList = []
    now = datetime.now(timezone.utc)
    year = now.year
    if incluede_current_month:
        month = now.month
    else:
        month = now.month - 1
        if month == 0:
            month = 12
            year -= 1

    consecutive_empty = 0
    while True:
        filtered_mrs = filterMergeRequestsByMergedAtMonth(merge_requests, year, month)
        if not filtered_mrs:
            consecutive_empty += 1
        else:
            consecutive_empty = 0
            stats = mergeRequestStats(filtered_mrs)
            stats["year"] = year
            stats["month"] = month
            statList.append(stats)

        if consecutive_empty >= max_consecutive_empty:
            break

        month -= 1
        if month == 0:
            month = 12
            year -= 1
        if year < 2000:
            break

    with open(
        f"./{project_name}/mrStatsGroupedByMergedAtMonthly.csv",
        mode="w",
        newline="",
        encoding="utf-8",
    ) as csvfile:
        fieldnames = [
            "year",
            "month",
            "total",
            "merged",
            "percentageMerged",
            "avgTimeToMergeSeconds",
            "avgTimeToMergeDHMS",
            "medianTimeToMergeSeconds",
            "medianTimeToMergeDHMS",
            "maxTimeToMergeSeconds",
            "maxTimeToMergeDHMS",
            "minTimeToMergeSeconds",
            "minTimeToMergeDHMS",
            "stdDevPopulationTimeToMergeSeconds",
            "stdDevPopulationTimeToMergeDHMS",
            "stdDevSampleTimeToMergeSeconds",
            "stdDevSampleTimeToMergeDHMS",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for stat in statList:
            writer.writerow(
                {
                    "year": stat["year"],
                    "month": stat["month"],
                    "total": stat["total"],
                    "merged": stat["merged"],
                    "percentageMerged": stat["percentageMerged"],
                    "avgTimeToMergeSeconds": stat["avgTimeToMergeSeconds"],
                    "avgTimeToMergeDHMS": stat["avgTimeToMergeDHMS"],
                    "medianTimeToMergeSeconds": stat["medianTimeToMergeSeconds"],
                    "medianTimeToMergeDHMS": stat["medianTimeToMergeDHMS"],
                    "maxTimeToMergeSeconds": stat["maxTimeToMergeSeconds"],
                    "maxTimeToMergeDHMS": stat["maxTimeToMergeDHMS"],
                    "minTimeToMergeSeconds": stat["minTimeToMergeSeconds"],
                    "minTimeToMergeDHMS": stat["minTimeToMergeDHMS"],
                    "stdDevPopulationTimeToMergeSeconds": stat[
                        "stdDevPopulationTimeToMergeSeconds"
                    ],
                    "stdDevPopulationTimeToMergeDHMS": stat[
                        "stdDevPopulationTimeToMergeDHMS"
                    ],
                    "stdDevSampleTimeToMergeSeconds": stat[
                        "stdDevSampleTimeToMergeSeconds"
                    ],
                    "stdDevSampleTimeToMergeDHMS": stat["stdDevSampleTimeToMergeDHMS"],
                }
            )

    return statList


def summaryCSVMergeRequestsByMergedAtYearly(
    merge_requests, project_name, max_consecutive_empty=1, incluede_current_year=False
):
    """Summary grouped by the MR `merged_at` year. Stops after `max_consecutive_empty` empty years."""
    statList = []
    now = datetime.now(timezone.utc)
    year = now.year if incluede_current_year else now.year - 1
    consecutive_empty = 0
    while True:
        filtered_mrs = filterMergeRequestsByMergedAtYear(merge_requests, year)
        if not filtered_mrs:
            consecutive_empty += 1
        else:
            consecutive_empty = 0
            stats = mergeRequestStats(filtered_mrs)
            stats["year"] = year
            statList.append(stats)
        if consecutive_empty >= max_consecutive_empty:
            break
        year -= 1
        if year < 2000:
            break
    with open(
        f"./{project_name}/mrStatsGroupedByMergedAtYearly.csv",
        mode="w",
        newline="",
        encoding="utf-8",
    ) as csvfile:
        fieldnames = [
            "year",
            "total",
            "merged",
            "open",
            "closed",
            "finished",
            "percentageMerged",
            "percentageClosed",
            "percentageFinished",
            "avgTimeToMergeSeconds",
            "avgTimeToMergeDHMS",
            "medianTimeToMergeSeconds",
            "medianTimeToMergeDHMS",
            "maxTimeToMergeSeconds",
            "maxTimeToMergeDHMS",
            "minTimeToMergeSeconds",
            "minTimeToMergeDHMS",
            "stdDevPopulationTimeToMergeSeconds",
            "stdDevPopulationTimeToMergeDHMS",
            "stdDevSampleTimeToMergeSeconds",
            "stdDevSampleTimeToMergeDHMS",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for stat in statList:
            writer.writerow(
                {
                    "year": stat["year"],
                    "total": stat["total"],
                    "merged": stat["merged"],
                    "open": stat["open"],
                    "closed": stat["closed"],
                    "finished": stat["finished"],
                    "percentageMerged": stat["percentageMerged"],
                    "percentageClosed": stat["percentageClosed"],
                    "percentageFinished": stat["percentageFinished"],
                    "avgTimeToMergeSeconds": stat["avgTimeToMergeSeconds"],
                    "avgTimeToMergeDHMS": stat["avgTimeToMergeDHMS"],
                    "medianTimeToMergeSeconds": stat["medianTimeToMergeSeconds"],
                    "medianTimeToMergeDHMS": stat["medianTimeToMergeDHMS"],
                    "maxTimeToMergeSeconds": stat["maxTimeToMergeSeconds"],
                    "maxTimeToMergeDHMS": stat["maxTimeToMergeDHMS"],
                    "minTimeToMergeSeconds": stat["minTimeToMergeSeconds"],
                    "minTimeToMergeDHMS": stat["minTimeToMergeDHMS"],
                    "stdDevPopulationTimeToMergeSeconds": stat[
                        "stdDevPopulationTimeToMergeSeconds"
                    ],
                    "stdDevPopulationTimeToMergeDHMS": stat[
                        "stdDevPopulationTimeToMergeDHMS"
                    ],
                    "stdDevSampleTimeToMergeSeconds": stat[
                        "stdDevSampleTimeToMergeSeconds"
                    ],
                    "stdDevSampleTimeToMergeDHMS": stat["stdDevSampleTimeToMergeDHMS"],
                }
            )

    return statList


def summaryCSVMergeRequestsByClosedAtMonthly(
    merge_requests, project_name, max_consecutive_empty=1, incluede_current_month=False
):
    """Summary grouped by the MR `closed_at` month. Stops after `max_consecutive_empty` empty months."""
    statList = []
    now = datetime.now(timezone.utc)
    year = now.year
    if incluede_current_month:
        month = now.month
    else:
        month = now.month - 1
        if month == 0:
            month = 12
            year -= 1
    consecutive_empty = 0
    while True:
        filtered_mrs = filterMergeRequestsByClosedAtMonth(merge_requests, year, month)
        if not filtered_mrs:
            consecutive_empty += 1
        else:
            consecutive_empty = 0
            stats = mergeRequestStats(filtered_mrs)
            stats["year"] = year
            stats["month"] = month
            statList.append(stats)
        if consecutive_empty >= max_consecutive_empty:
            break
        month -= 1
        if month == 0:
            month = 12
            year -= 1
        if year < 2000:
            break
    with open(
        f"./{project_name}/mrStatsGroupedByClosedAtMonthly.csv",
        mode="w",
        newline="",
        encoding="utf-8",
    ) as csvfile:
        fieldnames = [
            "year",
            "month",
            "total",
            "closed",
            "percentageClosed",
            "avgTimeToCloseSeconds",
            "avgTimeToCloseDHMS",
            "medianTimeToCloseSeconds",
            "medianTimeToCloseDHMS",
            "maxTimeToCloseSeconds",
            "maxTimeToCloseDHMS",
            "minTimeToCloseSeconds",
            "minTimeToCloseDHMS",
            "stdDevPopulationTimeToCloseSeconds",
            "stdDevPopulationTimeToCloseDHMS",
            "stdDevSampleTimeToCloseSeconds",
            "stdDevSampleTimeToCloseDHMS",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for stat in statList:
            writer.writerow(
                {
                    "year": stat["year"],
                    "month": stat["month"],
                    "total": stat["total"],
                    "closed": stat["closed"],
                    "percentageClosed": stat["percentageClosed"],
                    "avgTimeToCloseSeconds": stat["avgTimeToCloseSeconds"],
                    "avgTimeToCloseDHMS": stat["avgTimeToCloseDHMS"],
                    "medianTimeToCloseSeconds": stat["medianTimeToCloseSeconds"],
                    "medianTimeToCloseDHMS": stat["medianTimeToCloseDHMS"],
                    "maxTimeToCloseSeconds": stat["maxTimeToCloseSeconds"],
                    "maxTimeToCloseDHMS": stat["maxTimeToCloseDHMS"],
                    "minTimeToCloseSeconds": stat["minTimeToCloseSeconds"],
                    "minTimeToCloseDHMS": stat["minTimeToCloseDHMS"],
                    "stdDevPopulationTimeToCloseSeconds": stat[
                        "stdDevPopulationTimeToCloseSeconds"
                    ],
                    "stdDevPopulationTimeToCloseDHMS": stat[
                        "stdDevPopulationTimeToCloseDHMS"
                    ],
                    "stdDevSampleTimeToCloseSeconds": stat[
                        "stdDevSampleTimeToMergeSeconds"
                    ],
                    "stdDevSampleTimeToCloseDHMS": stat["stdDevSampleTimeToCloseDHMS"],
                }
            )

    return statList


def summaryCSVMergeRequestsByClosedAtYearly(
    merge_requests, project_name, max_consecutive_empty=1, incluede_current_year=False
):
    """Summary grouped by the MR `closed_at` year. Stops after `max_consecutive_empty` empty years."""
    statList = []
    now = datetime.now(timezone.utc)
    year = now.year if incluede_current_year else now.year - 1
    consecutive_empty = 0
    while True:
        filtered_mrs = filterMergeRequestsByClosedAtYear(merge_requests, year)
        if not filtered_mrs:
            consecutive_empty += 1
        else:
            consecutive_empty = 0
            stats = mergeRequestStats(filtered_mrs)
            stats["year"] = year
            statList.append(stats)
        if consecutive_empty >= max_consecutive_empty:
            break
        year -= 1
        if year < 2000:
            break
    with open(
        f"./{project_name}/mrStatsGroupedByClosedAtYearly.csv",
        mode="w",
        newline="",
        encoding="utf-8",
    ) as csvfile:
        fieldnames = [
            "year",
            "total",
            "closed",
            "percentageClosed",
            "avgTimeToCloseSeconds",
            "avgTimeToCloseDHMS",
            "medianTimeToCloseSeconds",
            "medianTimeToCloseDHMS",
            "maxTimeToCloseSeconds",
            "maxTimeToCloseDHMS",
            "minTimeToCloseSeconds",
            "minTimeToCloseDHMS",
            "stdDevPopulationTimeToCloseSeconds",
            "stdDevPopulationTimeToCloseDHMS",
            "stdDevSampleTimeToCloseSeconds",
            "stdDevSampleTimeToCloseDHMS",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for stat in statList:
            writer.writerow(
                {
                    "year": stat["year"],
                    "total": stat["total"],
                    "closed": stat["closed"],
                    "percentageClosed": stat["percentageClosed"],
                    "avgTimeToCloseSeconds": stat["avgTimeToCloseSeconds"],
                    "avgTimeToCloseDHMS": stat["avgTimeToCloseDHMS"],
                    "medianTimeToCloseSeconds": stat["medianTimeToCloseSeconds"],
                    "medianTimeToCloseDHMS": stat["medianTimeToCloseDHMS"],
                    "maxTimeToCloseSeconds": stat["maxTimeToCloseSeconds"],
                    "maxTimeToCloseDHMS": stat["maxTimeToCloseDHMS"],
                    "minTimeToCloseSeconds": stat["minTimeToCloseSeconds"],
                    "minTimeToCloseDHMS": stat["minTimeToCloseDHMS"],
                    "stdDevPopulationTimeToCloseSeconds": stat[
                        "stdDevPopulationTimeToCloseSeconds"
                    ],
                    "stdDevPopulationTimeToCloseDHMS": stat[
                        "stdDevPopulationTimeToCloseDHMS"
                    ],
                    "stdDevSampleTimeToCloseSeconds": stat[
                        "stdDevSampleTimeToMergeSeconds"
                    ],
                    "stdDevSampleTimeToCloseDHMS": stat["stdDevSampleTimeToCloseDHMS"],
                }
            )

    return statList


def summaryMDMergeRequestsByCreatedAtLastNDays(merge_requests, project_name, n_days):
    """Generate a markdown summary of MR stats for the last N days based on created_at."""
    end_date = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start_date = end_date - timedelta(days=n_days)
    filtered_mrs = filterMergeRequestsByCreatedAtTimeRange(
        merge_requests, start_date, end_date
    )
    stats = mergeRequestStats(filtered_mrs)

    markdown_multi_line = (
        f"## Merge Request Summary for the Last {n_days} Days (Created At)\n\n"
    )
    markdown_multi_line += f"- Total Merge Requests Created: {stats['total']}\n"
    markdown_multi_line += (
        f"- Of those Merged: {stats['merged']} ({stats['percentageMerged']:.2f}%)\n"
    )
    markdown_multi_line += f"- Of those Open: {stats['open']}\n"
    markdown_multi_line += (
        f"- Of those Closed: {stats['closed']} ({stats['percentageClosed']:.2f}%)\n"
    )
    markdown_multi_line += f"- Of those Finished: {stats['finished']} ({stats['percentageFinished']:.2f}%)\n"
    markdown_multi_line += f"- Average Time to Merge: {stats['avgTimeToMergeDHMS']}\n"
    markdown_multi_line += f"- Average Time to Close: {stats['avgTimeToCloseDHMS']}\n"
    markdown_multi_line += "\n"

    markdown_single_line = f"Created: {stats['total']}; "

    with open(
        f"./{project_name}/mrSummaryLast{n_days}Days.md", mode="a", encoding="utf-8"
    ) as mdfile:
        mdfile.write(markdown_multi_line)

    print(f"Markdown summary for last {n_days} days (created_at) created.")

    return markdown_multi_line, markdown_single_line, stats


def summaryMDMergeRequestsByMergedAtLastNDays(merge_requests, project_name, n_days):
    """Generate a markdown summary of MR stats for the last N days based on merged_at."""
    end_date = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start_date = end_date - timedelta(days=n_days)
    filtered_mrs = filterMergeRequestsByMergedAtTimeRange(
        merge_requests, start_date, end_date
    )
    stats = mergeRequestStats(filtered_mrs)

    markdown_multi_line = (
        f"## Merge Request Summary for the Last {n_days} Days (Merged At)\n\n"
    )
    markdown_multi_line += f"- Total Merge Requests Merged: {stats['total']}\n"
    markdown_multi_line += f"- Average Time to Merge: {stats['avgTimeToMergeDHMS']}\n"
    markdown_multi_line += "\n"

    markdown_single_line = f"Merged: {stats['total']}; "

    with open(
        f"./{project_name}/mrSummaryLast{n_days}Days.md", mode="a", encoding="utf-8"
    ) as mdfile:
        mdfile.write(markdown_multi_line)

    print(f"Markdown summary for last {n_days} days (merged_at) created.")

    return markdown_multi_line, markdown_single_line, stats


def summaryMDMergeRequestsByClosedAtLastNDays(merge_requests, project_name, n_days):
    """Generate a markdown summary of MR stats for the last N days based on closed_at."""
    end_date = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start_date = end_date - timedelta(days=n_days)
    filtered_mrs = filterMergeRequestsByClosedAtTimeRange(
        merge_requests, start_date, end_date
    )
    stats = mergeRequestStats(filtered_mrs)

    markdown_multi_line = (
        f"## Merge Request Summary for the Last {n_days} Days (Closed At)\n\n"
    )
    markdown_multi_line += f"- Total Merge Requests: {stats['total']}\n"
    markdown_multi_line += f"- Average Time to Close: {stats['avgTimeToCloseDHMS']}\n"
    markdown_multi_line += "\n"

    markdown_single_line = f"Closed: {stats['total']}; "

    with open(
        f"./{project_name}/mrSummaryLast{n_days}Days.md", mode="a", encoding="utf-8"
    ) as mdfile:
        mdfile.write(markdown_multi_line)

    print(f"Markdown summary for last {n_days} days (closed_at) created.")

    return markdown_multi_line, markdown_single_line, stats


def summaryMDMergeRequestsOpenFinished(merge_requests, project_name):
    """Generate a markdown summary of MR stats for open and finished MRs."""
    (
        filtered_open_mrs,
        filtered_finished_mrs,
        filtered_merged_mrs,
        filtered_closed_mrs,
    ) = filterMergeRequestsOpenFinished(merge_requests)

    markdown_multi_line = (
        "## Merge Request Summary Open and Finished(Merged or Closed)\n\n"
    )
    markdown_multi_line += f"- Total Merge Requests: {len(filtered_open_mrs) + len(filtered_finished_mrs)}\n"
    markdown_multi_line += f"- Of those Open: {len(filtered_open_mrs)}\n"
    markdown_multi_line += f"- Of those Merged: {len(filtered_merged_mrs)}\n"
    markdown_multi_line += f"- Of those Closed: {len(filtered_closed_mrs)}\n"
    markdown_multi_line += f"- Of those Finished: {len(filtered_finished_mrs)}\n"
    markdown_multi_line += "\n"

    markdown_single_line = (
        f"Total: {len(filtered_open_mrs) + len(filtered_finished_mrs)}; "
        f"Open: {len(filtered_open_mrs)};"
        f" Merged: {len(filtered_merged_mrs)}; "
        f"Closed: {len(filtered_closed_mrs)}; "
        f"Finished {len(filtered_finished_mrs)}; "
    )

    with open(
        f"./{project_name}/mrSummaryOpenFinished.md", mode="a", encoding="utf-8"
    ) as mdfile:
        mdfile.write(markdown_multi_line)

    print("Markdown summary for open and finished created.")

    return markdown_multi_line, markdown_single_line


def analyzeProjectMergeRequests(
    project_id, project_name, token, created_after=None, created_before=None
):
    """Fetch, export, and analyze merge requests for a given project."""

    markdown_summery = ""

    os.makedirs(f"./{project_name}", exist_ok=True)

    print("Fetching merge requests for project:", project_id, "/", project_name)

    merge_requests = getMergeRequests(project_id, token, created_after, created_before)
    print(len(merge_requests), "merge requests found and saved.")

    exportMergeRequestsToCSV(merge_requests, f"./{project_name}/merge_requests.csv")
    print("Merge requests exported to merge_requests.csv")

    markdown_summery = analyzeMergeRequests(project_name, merge_requests)

    return merge_requests, markdown_summery


def analyzeMergeRequests(project_name, merge_requests):
    """Analyze merge requests and generate summaries and CSV reports."""

    markdown_summery = ""

    print(f"----- Analyse {project_name} Merge Requests -----")

    print("----- Open Finished Filters -----")
    markdown_multi_line_open_finished, markdown_single_line_open_finished = (
        summaryMDMergeRequestsOpenFinished(merge_requests, project_name)
    )

    print("----- Created At Filters -----")
    summaryCSVMergeRequestsByCreatedAtMonthly(merge_requests, project_name, 3)
    summaryCSVMergeRequestsByCreatedAtYearly(
        merge_requests, project_name, 3, incluede_current_year=True
    )
    (
        markdown_multi_line_cre_at_l30,
        markdown_single_line_cre_at_l30,
        stats_cre_at_l30,
    ) = summaryMDMergeRequestsByCreatedAtLastNDays(merge_requests, project_name, 30)
    # (
    #    markdown_multi_line_cre_at_l7,
    #    markdown_single_line_cre_at_l7,
    #    stats_cre_at_l7,
    # ) = summaryMDMergeRequestsByCreatedAtLastNDays(merge_requests, project_name, 7)

    print("----- Merged At Filters -----")
    summaryCSVMergeRequestsByMergedAtMonthly(merge_requests, project_name, 3)
    summaryCSVMergeRequestsByMergedAtYearly(
        merge_requests, project_name, 3, incluede_current_year=True
    )
    (
        markdown_multi_line_mer_at_l30,
        markdown_single_line_mer_at_l30,
        stats_mer_at_l30,
    ) = summaryMDMergeRequestsByMergedAtLastNDays(merge_requests, project_name, 30)
    # (
    #    markdown_multi_line_mer_at_l7,
    #    markdown_single_line_mer_at_l7,
    #    stats_mer_at_l7,
    # ) = summaryMDMergeRequestsByMergedAtLastNDays(merge_requests, project_name, 7)

    print("----- Closed At Filters -----")
    summaryCSVMergeRequestsByClosedAtMonthly(merge_requests, project_name, 3)
    summaryCSVMergeRequestsByClosedAtYearly(
        merge_requests, project_name, 3, incluede_current_year=True
    )
    (
        markdown_multi_line_clo_at_l30,
        markdown_single_line_clo_at_l30,
        stats_clo_at_l30,
    ) = summaryMDMergeRequestsByClosedAtLastNDays(merge_requests, project_name, 30)
    # (
    #    markdown_multi_line_clo_at_l7,
    #    markdown_single_line_clo_at_l7,
    #    stats_clo_at_l7,
    # ) = summaryMDMergeRequestsByClosedAtLastNDays(merge_requests, project_name, 7)

    end_date = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    markdown_summery += f"\n\n### Merge Request Summary of {project_name}\n"
    markdown_summery += (
        "**Total Merge Request**: " + markdown_single_line_open_finished + "<br>\n"
    )

    start_date = end_date - timedelta(days=30)
    markdown_summery += (
        f"**Last 30 Days** (From {start_date.strftime('%Y-%m-%d')} To"
        f" {end_date.strftime('%Y-%m-%d')}): "
    )
    markdown_summery += markdown_single_line_cre_at_l30
    markdown_summery += markdown_single_line_mer_at_l30
    markdown_summery += "New " + markdown_single_line_cre_at_l30
    markdown_summery += markdown_single_line_clo_at_l30
    markdown_summery += (
        f"<br>\nLast 30 Days median time to merge new: {stats_cre_at_l30['medianTimeToMergeDHMS']}, "
        f"median time to merge: {stats_mer_at_l30['medianTimeToMergeDHMS']}; "
    )

    # start_date = end_date - timedelta(days=7)
    # markdown_summery += f"\n#### Last 7 Days (From {start_date} To {end_date})\n"
    # markdown_summery += markdown_single_line_cre_at_l7
    # markdown_summery += markdown_single_line_mer_at_l7
    # markdown_summery += markdown_single_line_clo_at_l7

    return markdown_summery


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="List GitLab merge requests using python-gitlab"
    )
    p.add_argument(
        "--project",
        help="Project ID or path (e.g. 'namespace/project' or numeric id)",
        default=None,
        required=False,
    )
    p.add_argument(
        "--token",
        help="GitLab token (or set GITLAB_TOKEN)",
        default=os.getenv("GITLAB_TOKEN"),
    )
    p.add_argument(
        "--after",
        help="created_after ISO date (e.g. 2024-01-01T00:00:00Z)",
        default=None,
    )
    p.add_argument(
        "--before",
        help="created_before ISO date (e.g. 2024-12-31T23:59:59Z)",
        default=None,
    )
    p.add_argument(
        "--path",
        help="sets the target path where to store the results",
        default=None,
    )
    args = p.parse_args()

    if not args.token:
        print("GITLAB token not provided. Set GITLAB_TOKEN or pass --token.")
        args.token = ""

    if args.path is not None:
        os.makedirs(args.path, exist_ok=True)
        os.chdir(args.path)

    merge_requests = []
    markdown_summery = ""

    if args.project is not None:
        merge_requests, markdown_summery = analyzeProjectMergeRequests(
            args.project, "Parameter_Project", args.token, args.after, args.before
        )

    else:
        for project in project_ids:
            print(f"===== Analyzing Project: {project} =====")
            tmp_merge_requests, markdown_summery_tmp = analyzeProjectMergeRequests(
                project_ids[project], project, args.token, args.after, args.before
            )
            merge_requests.extend(tmp_merge_requests)
            markdown_summery += markdown_summery_tmp

        print("===== Analyzing Total =====")
        os.makedirs("./Total", exist_ok=True)
        markdown_summery_tmp = analyzeMergeRequests("Total", merge_requests)
        markdown_summery = markdown_summery_tmp + markdown_summery

    print("----- Final Summary -----")
    print(markdown_summery)
    with open("./shortMDSummery.md", mode="w", encoding="utf-8") as mdfile:
        mdfile.write(markdown_summery)
