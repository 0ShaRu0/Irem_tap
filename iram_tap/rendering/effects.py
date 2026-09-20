from collections.abc import Iterator


def glow_rings(width: float, height: float, alpha: int) -> Iterator[tuple[float, float, int]]:
    """Shared geometry/alpha policy; backends decide pixel rasterization."""
    for step in range(12, 0, -1):
        fraction = step / 12
        yield width * fraction, height * fraction, round(alpha * (1.0 - fraction * 0.72))
