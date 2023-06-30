"""
Generic geometric utils
"""
from dataclasses import dataclass
import math


@dataclass
class Vec2D:
    """
    A 2D vector - an x and y value
    """

    x: float
    y: float

    def __sub__(self, other: "Vec2D") -> "Vec2D":
        return Vec2D(other.x - self.x, other.y - self.y)

    def __add__(self, other: "Vec2D") -> "Vec2D":
        return Vec2D(other.x + self.x, other.y + self.y)

    def __abs__(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y)

    def length(self) -> float:
        return abs(self)

    def __str__(self) -> str:
        return f"({self.x}, {self.y})"

    @staticmethod
    def lexicographic_key(vec) -> tuple:
        """
        Get a lexicographically-sorted tuple that allows to strictly order vectors
        when sorting.
        """
        return (vec.x, vec.y)

    @property
    def angle(self) -> float:
        """
        Get the angle of the vector (mathematical style: 0 radians is 3-o-clock)
        """
        if self.x == 0:
            theta = math.pi / 2
        else:
            theta = math.atan(self.y / self.x)
        return theta

    @property
    def manhattan_length(self):
        return self.x + self.y


@dataclass
class Point:
    """
    A geometric point, defined as a vector from the origin
    """

    vec: Vec2D

    def __init__(self, x: float, y: float):
        """
        Create a point at a given location
        """
        self.vec = Vec2D(x, y)

    @property
    def x(self) -> float:
        """
        The point's x coordinate
        """
        return self.vec.x

    @property
    def y(self) -> float:
        """
        The point's y coordinate
        """
        return self.vec.y

    def __str__(self) -> str:
        return f"Point({self.vec.x}, {self.vec.y})"

    @staticmethod
    def lexicographic_key(pt) -> tuple:
        """
        Get a lexicographically-sorted tuple that allows to strictly order points
        when sorting.
        """
        return Vec2D.lexicographic_key(pt.vec)

    def from_origin(self) -> Vec2D:
        """
        The vector from the origin to this point"""
        return self.vec

    def vec_to(self, other: "Point") -> Vec2D:
        """
        The vector from this point to another point
        """
        return other.vec - self.vec

    def distance_to(self, other: "Point") -> float:
        """
        The distance to another point
        """
        return abs(self.vec_to(other))

    def angle_to(self, other: "Point") -> float:
        """
        The angle, in radians, to another point
        """
        return self.vec_to(other).angle


@dataclass
class Seg2D:
    """
    A 2D line segment, which is defined as a line joining two points
    """

    start: Point
    end: Point

    def __init__(self, start, end):
        self.start = start
        self.end = end

    def __abs__(self) -> float:
        return abs(self.vector)

    def __str__(self) -> str:
        return f"Seg(({self.start.x}, {self.start.y}) -> ({self.end.x}, {self.end.y}))"

    @property
    def vector(self) -> Vec2D:
        """
        Get the vector of the segment (i.e. the line if p1 was the origin)
        """
        return self.start.vec_to(self.end)

    @property
    def length(self) -> float:
        return abs(self.vector)

    @property
    def angle(self) -> float:
        return self.vector.angle

    @property
    def manhattan_length(self) -> float:
        return self.vector.manhattan_length

    def lexicographically_ordered(self) -> "Seg2D":
        """
        Get a segment that has both points in lexicographic order

        So P(A, B).lexicographically_ordered() and P(B, A).lexicographically_ordered()
        will return the same result
        """
        s_e = sorted((self.start, self.end), key=Point.lexicographic_key)
        return Seg2D(s_e[0], s_e[1])
