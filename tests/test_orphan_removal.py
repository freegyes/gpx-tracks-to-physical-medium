"""Tests for flood-fill orphan removal (used for both borders and rivers)."""

from shapely.geometry import LineString

from gpx2fab.geometry import remove_orphan_geometries


class TestRemoveOrphanGeometries:
    def _square_seed(self):
        """A buffered square as seed zone."""
        return LineString([(0, 0), (1000, 0), (1000, 1000), (0, 1000), (0, 0)]).buffer(500)

    def test_connected_kept(self):
        seed = self._square_seed()
        connected = LineString([(1000, 500), (1500, 500)])
        result = remove_orphan_geometries([connected], seed, tolerance=500)
        assert len(result) == 1

    def test_disconnected_removed(self):
        seed = self._square_seed()
        orphan = LineString([(5000, 5000), (6000, 5000)])
        result = remove_orphan_geometries([orphan], seed, tolerance=500)
        assert len(result) == 0

    def test_chain_propagation(self):
        """Segments connected through intermediaries should all be kept."""
        seed = self._square_seed()
        seg1 = LineString([(1000, 500), (1500, 500)])
        seg2 = LineString([(1500, 500), (2000, 500)])  # touches seg1, not seed
        result = remove_orphan_geometries([seg1, seg2], seed, tolerance=500)
        assert len(result) == 2

    def test_mixed_connected_and_orphan(self):
        seed = self._square_seed()
        connected = LineString([(1000, 500), (1500, 500)])
        orphan = LineString([(5000, 5000), (6000, 5000)])
        result = remove_orphan_geometries([connected, orphan], seed, tolerance=500)
        assert len(result) == 1

    def test_empty_input_returns_empty(self):
        seed = self._square_seed()
        assert remove_orphan_geometries([], seed) == []

    def test_preserves_order(self):
        seed = self._square_seed()
        a = LineString([(1000, 500), (1500, 500)])
        b = LineString([(1500, 500), (2000, 500)])
        # Pass in reverse order — result should preserve original indices
        result = remove_orphan_geometries([b, a], seed, tolerance=500)
        # 'a' touches seed first during iteration, but both end up connected;
        # result order should match input order
        assert len(result) == 2
        assert result[0].equals(b)
        assert result[1].equals(a)
