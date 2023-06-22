# -*- coding: utf-8 -*-
import math

from rules_symbol.rule import KLCRule


class Rule(KLCRule):
    """Basic geometry checks"""

    # set thresholds for tested angle
    verySmallAngle = math.radians(0.4)

    smallLength = 0.1  # in mm, about 4 thou

    def _check_degenerate_arcs(self):
        for arc in self.component.arcs:
            d_start_mid = arc.start.distance_to(arc.midpoint)
            d_end_mid = arc.end.distance_to(arc.midpoint)
            d_start_end = arc.start.distance_to(arc.end)

            if d_start_mid < self.smallLength or d_end_mid < self.smallLength:
                self.warning(
                    f"Arc has zero or near-zero size: start {arc.start}, mid {arc.end}, end {arc.end}"
                )
            elif d_start_end < self.smallLength:
                self.warning(
                    f"Arc starts and ends in the same place ({arc.start}): is it a circle?"
                )

    def _check_degenerate_polylines(self):
        for polyline in self.component.polylines:
            n_points = len(polyline.points)
            segment_i = 0
            if n_points == 0:
                self.warning("Polyline contains no points")
            elif n_points == 1:
                self.warning(
                    f"Polyline contains only a single point: {polyline.points[0]}"
                )
            else:
                # do segment-by-segment checks
                for seg in polyline.get_segs():
                    if seg.length < self.smallLength:
                        self.warning(
                            f"Polyline contains a zero or near-zero length segment "
                            f"(segment {segment_i + 1} of {n_points - 1}): "
                            f" {seg}, length {seg.length:04f}"
                        )

                    theta = seg.angle
                    theta_deviation = math.radians(45) - abs(
                        math.radians(45) - (theta % math.radians(90))
                    )

                    if theta_deviation > 0 and theta_deviation < self.verySmallAngle:
                        degrees = math.degrees(theta)
                        self.warning(
                            "Polyline contains a segment that is nearly but not exactly horizontal or vertical "
                            f"(segment {segment_i + 1} of {n_points - 1}): "
                            f"segment {seg} is {degrees:04f} degrees"
                        )

                    segment_i += 1

    def _check_duplicate_segments(self):
        segs = {}

        for polyline in self.component.polylines:
            for seg in polyline.get_segs():
                if seg in segs:
                    self.warning(f"The same segment exists multiple times: {seg}")
                else:
                    segs[seg] = True

    def _check_duplicate_circles(self):
        circles = {}

        for circle in self.component.circles:
            circ_key = (circle.center.pt.from_origin(), circle.radius)
            if circ_key in circles:
                self.warning(
                    "The same circle geometry exists multiple times:"
                    f"{circle.center.pt}, radius {circle.radius}"
                )
            else:
                circles[circ_key] = True

    def _check_duplicate_arcs(self):
        arcs = {}

        for arc in self.component.arcs:
            arc_key = (
                arc.start.from_origin(),
                arc.midpoint.from_origin(),
                arc.end.from_origin(),
            )
            if arc_key in arcs:
                self.warning(
                    "The same arc geometry exists multiple times:"
                    f"{arc.start}, midpoint {arc.midpoint}, end {arc.end}"
                )
            else:
                arcs[arc_key] = True

    def check(self):
        """
        Proceeds the checking of the rule.
        """
        self._check_degenerate_arcs()
        self._check_degenerate_polylines()

        # very small circles are just dots
        # and that's probably OK

        self._check_duplicate_segments()
        self._check_duplicate_circles()
        self._check_duplicate_arcs()

        return 0  # There is no KLC rule for this so this check only generates warnings

    def fix(self):
        """
        Proceeds the fixing of the rule, if possible.
        """
        return
