# GPX Tracks to Physical Medium

Tools for turning GPS tracks and open map data into fabrication-ready SVG files for pen plotters and laser cutters.

The idea: take a GPX file, pull in surrounding geography from openly available datasets, and produce layered SVGs that go straight to a plotter or a laser cutter with no manual post-processing. Each project lives in its own subdirectory with its own inputs, generation script, and output files.

This is still a single-purpose repo -- right now it does one thing well. Over time it may grow into a collection of map-to-fabrication recipes, and eventually into reusable tooling that lets others generate their own versions from a GPX file and a few parameters.

## Projects

### [Hungarian Blue Trail](hungarian-blue-trail/)

A5 landscape notebook cover featuring Hungary's border, water features, and the 1172 km OKT ([Orszagos Kektura](https://en.wikipedia.org/wiki/National_Blue_Trail)) hiking trail.

![Preview](hungarian-blue-trail/output/preview.png)

Outputs a pen-plotter SVG (4 AxiDraw layers) and a laser SVG (cut + engrave layers). See the [project README](hungarian-blue-trail/README.md) for details.
