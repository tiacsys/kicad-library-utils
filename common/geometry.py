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

    def __hash__(self) -> int:
        return hash((self.x, self.y))

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

    def __hash__(self) -> int:
        return hash(self.vec)

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

    p1: Point
    p2: Point
    # cache the vector as we need it for nearly everything
    _vec: Vec2D

    def __init__(self, p1, p2):
        self.p1 = p1
        self.p2 = p2
        self._vec = p1.vec_to(p2)

    def __hash__(self) -> int:
        return hash((self.p1, self.p2))

    def __abs__(self) -> float:
        return abs(self._vec)

    def __str__(self) -> str:
        return f"Seg(({self.p1.x}, {self.p1.y}) -> ({self.p2.x}, {self.p2.y}))"

    @property
    def vector(self) -> Vec2D:
        """
        Get the vector of the segment (i.e. the line if p1 was the origin)
        """
        return self._vec

    @property
    def length(self) -> float:
        return abs(self._vec)

    @property
    def angle(self) -> float:
        return self._vec.angle

    @property
    def manhattan_length(self) -> float:
        return self._vec.manhattan_length
