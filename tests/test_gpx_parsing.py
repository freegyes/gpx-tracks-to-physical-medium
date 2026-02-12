"""Tests for GPX parsing — both track and route formats."""

import textwrap

from gpx2fab.trail import parse_gpx


def _gpx_bytes(body: str) -> bytes:
    return textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <gpx version="1.1" creator="test"
             xmlns="http://www.topografix.com/GPX/1/1">
          {body}
        </gpx>
    """).encode("utf-8")


class TestParseGpx:
    def test_track_points(self):
        gpx = _gpx_bytes("""
            <trk><trkseg>
                <trkpt lat="47.5" lon="19.0"/>
                <trkpt lat="47.6" lon="19.1"/>
                <trkpt lat="47.7" lon="19.2"/>
            </trkseg></trk>
        """)
        points = parse_gpx(gpx)
        assert len(points) == 3
        assert points[0] == (19.0, 47.5)  # (lon, lat)
        assert points[2] == (19.2, 47.7)

    def test_route_points(self):
        gpx = _gpx_bytes("""
            <rte>
                <rtept lat="48.0" lon="17.0"/>
                <rtept lat="48.5" lon="18.0"/>
            </rte>
        """)
        points = parse_gpx(gpx)
        assert len(points) == 2
        assert points[0] == (17.0, 48.0)

    def test_mixed_tracks_and_routes(self):
        gpx = _gpx_bytes("""
            <trk><trkseg>
                <trkpt lat="47.0" lon="19.0"/>
                <trkpt lat="47.1" lon="19.1"/>
            </trkseg></trk>
            <rte>
                <rtept lat="48.0" lon="20.0"/>
            </rte>
        """)
        points = parse_gpx(gpx)
        assert len(points) == 3

    def test_empty_gpx(self):
        gpx = _gpx_bytes("")
        assert parse_gpx(gpx) == []

    def test_multi_segment_track(self):
        gpx = _gpx_bytes("""
            <trk>
                <trkseg>
                    <trkpt lat="47.0" lon="19.0"/>
                    <trkpt lat="47.1" lon="19.1"/>
                </trkseg>
                <trkseg>
                    <trkpt lat="48.0" lon="20.0"/>
                    <trkpt lat="48.1" lon="20.1"/>
                </trkseg>
            </trk>
        """)
        points = parse_gpx(gpx)
        assert len(points) == 4
